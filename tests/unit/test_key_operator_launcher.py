import json
import os
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "scripts" / "api_key_operator.sh"
BASH = shutil.which("bash")
OP = "11111111-1111-4111-8111-111111111111"
IMAGE = "sha256:" + "a" * 64
CANARY = "synthetic-private-profile-canary"
MASTER = "synthetic-private-master-canary"
pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or BASH is None or not Path("/proc/sys/kernel/random/uuid").is_file(),
    reason="Manual launcher requires Linux, Bash, and kernel UUID support",
)


@pytest.fixture
def launcher(tmp_path):
    if ROOT == tmp_path or ROOT in tmp_path.parents:
        pytest.skip("Private fixture must be outside the checkout")
    root = tmp_path / "operator root"
    root.mkdir(mode=0o700)
    for name in ("ciphertext", "delivery", "audit"):
        (root / name).mkdir(mode=0o700)
    for name, value in (
        ("operator-manual.env", f"ORACLE_PASSWORD={CANARY}\nOPERATOR_AUTHORIZED=True\n"),
        ("master.key", MASTER),
        ("operator-image.id", IMAGE + "\n"),
    ):
        path = root / name
        path.write_text(value)
        path.chmod(0o600)
    capture = tmp_path / "docker-calls.json"
    binary = tmp_path / "fake bin"
    binary.mkdir(mode=0o700)
    docker = binary / "docker"
    docker.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, stat, sys, time\n"
        "capture = pathlib.Path(os.environ['FAKE_DOCKER_CAPTURE'])\n"
        "audit = pathlib.Path(os.environ['FAKE_AUDIT_DIR'])\n"
        "before = {p.name: {'text': p.read_text(), 'mode': stat.S_IMODE(p.stat().st_mode)} "
        "for p in audit.iterdir() if p.is_file()}\n"
        "calls = json.loads(capture.read_text()) if capture.exists() else []\n"
        "calls.append({'argv': sys.argv[1:], 'audit_before': before})\n"
        "pending = capture.with_suffix('.pending')\n"
        "pending.write_text(json.dumps(calls))\n"
        "pending.replace(capture)\n"
        "time.sleep(float(os.environ.get('FAKE_DOCKER_SLEEP', '0')))\n"
        "args = sys.argv[1:]\n"
        "operation = args[args.index('--operation-id') + 1]\n"
        "code = int(os.environ.get('FAKE_DOCKER_EXIT_CODE', '0'))\n"
        "print(json.dumps({'ok': code == 0, 'operation_id': operation, "
        "'error_code': 'COMMIT_OUTCOME_UNKNOWN' if code == 4 else None}))\n"
        "print('synthetic-engine-diagnostic', file=sys.stderr)\n"
        "sys.exit(code)\n"
    )
    docker.chmod(0o700)
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    env = {
        "PATH": str(binary) + os.pathsep + os.environ.get("PATH", os.defpath),
        "HOME": str(home),
        "API_LOGISTIK_OPERATOR_ROOT": str(root),
        "FAKE_DOCKER_CAPTURE": str(capture),
        "FAKE_AUDIT_DIR": str(root / "audit"),
    }

    # The offline image mounts /tmp noexec; only the test double needs an interpreter.
    env["BASH_FUNC_docker%%"] = (
        f'() {{ exec {shlex.quote(sys.executable)} {shlex.quote(str(docker))} "$@"; }}'
    )

    def run(*args, updates=None):
        selected = env.copy()
        if updates:
            for name, value in updates.items():
                if value is None:
                    selected.pop(name, None)
                else:
                    selected[name] = value
        return subprocess.run(
            [BASH, str(LAUNCHER), *map(str, args)],
            cwd=ROOT,
            env=selected,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    def calls():
        return json.loads(capture.read_text()) if capture.exists() else []

    return SimpleNamespace(root=root, env=env, binary=binary, run=run, calls=calls)


def values(args, name):
    found = []
    for index, item in enumerate(args):
        if item == name:
            found.append(args[index + 1])
        elif item.startswith(name + "="):
            found.append(item.split("=", 1)[1])
    return found


def cli_arguments(call):
    args = call["argv"]
    image = args.index(IMAGE)
    assert args[image + 1] == "api-logistik-keys"
    return args[image + 2 :]


def no_docker(launcher, result):
    assert result.returncode != 0
    assert launcher.calls() == []
    assert CANARY not in result.stdout + result.stderr
    assert MASTER not in result.stdout + result.stderr


def without_docker_path(tmp_path):
    directory = tmp_path / "coreutils only"
    directory.mkdir(mode=0o700)
    for name in ("dirname", "realpath", "stat", "id", "date", "mktemp", "tee", "sync"):
        executable = shutil.which(name)
        if executable:
            (directory / name).symlink_to(executable)
    return str(directory)


def test_help_needs_neither_docker_nor_private_material(launcher, tmp_path):
    result = launcher.run(
        "--help",
        updates={
            "PATH": without_docker_path(tmp_path),
            "API_LOGISTIK_OPERATOR_ROOT": str(tmp_path / "absent"),
            "BASH_FUNC_docker%%": None,
        },
    )
    assert result.returncode == 0
    assert "status" in result.stdout and "prepare" in result.stdout
    assert launcher.calls() == []


@pytest.mark.parametrize(
    "args",
    [
        (),
        ("unknown",),
        ("tick",),
        ("init-secret-key",),
        ("status", "--env-file", "untrusted.env"),
        ("status", "--unknown"),
        ("status", "--manual"),
        ("status", ""),
        ("status", "--operation-id", OP, "--operation-id=" + OP),
        ("prepare", "--expected-version", "4"),
        ("prepare", "--reason", "scheduled"),
        ("prepare", "--expected-version", "not-an-int", "--reason", "scheduled"),
        ("prepare", "--expected-version", "-1", "--reason", "scheduled"),
        ("prepare", "--expected-version", "4", "--reason", CANARY),
        ("prepare", "--expected-version", "4", "--reason", "scheduled", "--manual"),
        ("prepare", "--expected-version", "4", "--expected-version=5", "--reason", "scheduled"),
        ("activate", "--expected-version", "4", "--reason", "scheduled", "--manual", "--emergency"),
        ("activate", "--expected-version", "4", "--reason", "scheduled", "--replace-pending"),
        ("confirm-distributed", "--key-id", "1", "--reason", "distribution_confirmed"),
        ("revoke", "--expected-version", "4", "--reason", "key_retired"),
        ("export", "--key-id", "0", "--output", "/tmp/invalid"),
        ("export", "--key-id", "1"),
        ("reconcile",),
        ("reconcile", "--operation-id", "not-a-uuid"),
    ],
)
def test_invalid_arguments_never_invoke_docker(launcher, args):
    no_docker(launcher, launcher.run(*args))


@pytest.mark.parametrize(
    "args",
    [
        ("status",),
        ("prepare", "--expected-version", "0", "--reason", "bootstrap"),
        ("prepare", "--expected-version", "4", "--reason", "scheduled", "--replace-pending"),
        ("prepare", "--expected-version", "4", "--reason", "suspected_compromise", "--emergency"),
        (
            "prepare",
            "--expected-version=4",
            "--reason=scheduled",
            "--emergency",
            "--replace-pending",
        ),
        (
            "confirm-distributed",
            "--key-id",
            "1",
            "--expected-version",
            "4",
            "--reason",
            "distribution_confirmed",
        ),
        ("activate", "--expected-version", "4", "--reason", "scheduled"),
        ("activate", "--expected-version", "4", "--reason", "manual_rotation", "--manual"),
        ("activate", "--expected-version", "4", "--reason", "suspected_compromise", "--emergency"),
        ("revoke", "--key-id", "1", "--expected-version", "4", "--reason", "key_retired"),
        ("reconcile", "--key-id", "1"),
    ],
)
def test_commands_forward_only_requested_arguments(launcher, args):
    result = launcher.run(*args, "--operation-id", OP)
    assert result.returncode == 0, result.stderr
    assert len(launcher.calls()) == 1
    cli = cli_arguments(launcher.calls()[0])
    assert cli[4:] == list(args)
    assert values(cli, "--operation-id") == [OP]
    assert values(cli, "--env-file") == [str(launcher.root / "operator-manual.env")]


@pytest.mark.parametrize(
    "reason",
    [
        "bootstrap",
        "scheduled",
        "manual_rotation",
        "suspected_compromise",
        "distribution_confirmed",
        "key_retired",
        "recovery",
    ],
)
def test_all_existing_reason_codes_are_supported(launcher, reason):
    result = launcher.run("prepare", "--expected-version", "1", "--reason", reason)
    assert result.returncode == 0, result.stderr
    assert values(cli_arguments(launcher.calls()[0]), "--reason") == [reason]


def test_generated_uuid_and_private_audit_precede_docker(launcher):
    result = launcher.run("status")
    assert result.returncode == 0, result.stderr
    (call,) = launcher.calls()
    (operation,) = values(cli_arguments(call), "--operation-id")
    assert str(UUID(operation)) == operation
    assert UUID(operation).version == 4
    name, intent = next(iter(call["audit_before"].items()))
    assert len(call["audit_before"]) == 1
    assert operation in intent["text"] and intent["mode"] == 0o600
    audit = launcher.root / "audit" / name
    assert "completed" in audit.read_text()
    assert stat.S_IMODE(audit.stat().st_mode) == 0o600


@pytest.mark.parametrize("exit_code", [0, 1, 2, 3, 4, 125, 126, 127])
def test_exit_codes_are_preserved_without_retry(launcher, exit_code):
    result = launcher.run(
        "status", "--operation-id", OP, updates={"FAKE_DOCKER_EXIT_CODE": str(exit_code)}
    )
    assert result.returncode == exit_code
    assert len(launcher.calls()) == 1
    assert "synthetic-engine-diagnostic" not in result.stdout + result.stderr
    if exit_code == 4:
        assert "RECONCILE_REQUIRED" in result.stderr


def test_reconcile_preserves_uuid_but_creates_distinct_audit(launcher):
    assert launcher.run("status", "--operation-id", OP).returncode == 0
    before = {path.name for path in (launcher.root / "audit").iterdir()}
    assert launcher.run("reconcile", "--operation-id", OP).returncode == 0
    assert len(launcher.calls()) == 2
    assert values(cli_arguments(launcher.calls()[1]), "--operation-id") == [OP]
    assert len(list((launcher.root / "audit").iterdir())) == len(before) + 1


def test_docker_is_pinned_hardened_and_does_not_receive_credentials(launcher):
    result = launcher.run("status", "--operation-id", OP)
    assert result.returncode == 0, result.stderr
    (call,) = launcher.calls()
    argv = call["argv"]
    assert argv[:3] == ["--context", "default", "run"] and argv.count(IMAGE) == 1
    docker_args = argv[: argv.index(IMAGE)]
    assert "--rm" in docker_args and "--read-only" in docker_args
    assert values(docker_args, "--pull") == ["never"]
    assert values(docker_args, "--user") == [f"{os.getuid()}:{os.getgid()}"]
    assert values(docker_args, "--tmpfs") == ["/tmp:rw,noexec,nosuid,size=128m"]
    assert values(docker_args, "--cap-drop") == ["ALL"]
    assert values(docker_args, "--security-opt") == ["no-new-privileges"]
    assert values(docker_args, "--env") == ["USER=local-operator"]
    assert not values(docker_args, "--env-file")
    assert not any(
        arg in ("-p", "-P", "--publish", "--publish-all", "--privileged") for arg in docker_args
    )
    assert "docker.sock" not in " ".join(argv)
    assert values(docker_args, "--mount") == [
        f"type=bind,source={launcher.root},target={launcher.root},readonly",
        f"type=bind,source={launcher.root}/ciphertext,target={launcher.root}/ciphertext",
        f"type=bind,source={launcher.root}/delivery,target={launcher.root}/delivery",
    ]
    audit = "".join(path.read_text() for path in (launcher.root / "audit").iterdir())
    assert CANARY not in result.stdout + result.stderr + json.dumps(argv) + audit
    assert MASTER not in result.stdout + result.stderr + json.dumps(argv) + audit


@pytest.mark.parametrize(
    "name",
    ["operator-manual.env", "master.key", "operator-image.id", "ciphertext", "delivery", "audit"],
)
def test_missing_private_material_prevents_docker(launcher, name):
    path = launcher.root / name
    if path.is_dir():
        path.rmdir()
    else:
        path.unlink()
    no_docker(launcher, launcher.run("status"))


@pytest.mark.parametrize("value", ["api-logistik:latest", "sha256:" + "a" * 63, IMAGE + "\nextra"])
def test_invalid_image_pin_prevents_docker(launcher, value):
    (launcher.root / "operator-image.id").write_text(value)
    no_docker(launcher, launcher.run("status"))


@pytest.mark.parametrize(
    "name,mode",
    [
        ("", 0o755),
        ("operator-manual.env", 0o644),
        ("master.key", 0o640),
        ("operator-image.id", 0o644),
        ("ciphertext", 0o755),
        ("delivery", 0o755),
        ("audit", 0o755),
    ],
)
def test_unsafe_permissions_prevent_docker(launcher, name, mode):
    (launcher.root / name).chmod(mode)
    no_docker(launcher, launcher.run("status"))


@pytest.mark.parametrize(
    "name",
    ["operator-manual.env", "master.key", "operator-image.id", "ciphertext", "delivery", "audit"],
)
def test_symlinked_material_prevents_docker(launcher, name):
    path = launcher.root / name
    target = path.with_name(path.name + ".real")
    path.rename(target)
    path.symlink_to(target, target_is_directory=target.is_dir())
    no_docker(launcher, launcher.run("status"))


def test_symlinked_root_and_ancestor_prevent_docker(launcher, tmp_path):
    alias = tmp_path / "alias"
    alias.symlink_to(launcher.root, target_is_directory=True)
    no_docker(launcher, launcher.run("status", updates={"API_LOGISTIK_OPERATOR_ROOT": str(alias)}))
    ancestor = tmp_path / "ancestor alias"
    ancestor.symlink_to(tmp_path, target_is_directory=True)
    no_docker(
        launcher,
        launcher.run(
            "status", updates={"API_LOGISTIK_OPERATOR_ROOT": str(ancestor / launcher.root.name)}
        ),
    )


def test_untrusted_writable_ancestor_prevents_docker(launcher, tmp_path):
    previous = stat.S_IMODE(tmp_path.stat().st_mode)
    try:
        tmp_path.chmod(0o777)
        no_docker(launcher, launcher.run("status"))
    finally:
        tmp_path.chmod(previous)


@pytest.mark.parametrize("suffix", [",comma", "\nnewline", ":colon", '"quote'])
def test_mount_delimiters_are_rejected(launcher, suffix):
    root = launcher.root.with_name(launcher.root.name + suffix)
    launcher.root.rename(root)
    no_docker(launcher, launcher.run("status", updates={"API_LOGISTIK_OPERATOR_ROOT": str(root)}))


def test_checkout_root_is_rejected_without_docker(launcher):
    no_docker(launcher, launcher.run("status", updates={"API_LOGISTIK_OPERATOR_ROOT": str(ROOT)}))


def test_missing_docker_fails_without_retry(launcher, tmp_path):
    result = launcher.run(
        "status", updates={"PATH": without_docker_path(tmp_path), "BASH_FUNC_docker%%": None}
    )
    assert result.returncode != 0 and "docker" in result.stderr.lower()
    assert launcher.calls() == []


@pytest.mark.parametrize("default", ["home", "xdg"])
def test_default_private_root_selection(launcher, tmp_path, default):
    base = (
        tmp_path / "data home" if default == "xdg" else Path(launcher.env["HOME"]) / ".local/share"
    )
    base.mkdir(parents=True, mode=0o700)
    root = base / "api-logistik"
    launcher.root.rename(root)
    updates = {"API_LOGISTIK_OPERATOR_ROOT": "", "FAKE_AUDIT_DIR": str(root / "audit")}
    if default == "xdg":
        updates["XDG_DATA_HOME"] = str(base)
    result = launcher.run("status", updates=updates)
    assert result.returncode == 0, result.stderr
    assert values(cli_arguments(launcher.calls()[0]), "--env-file") == [
        str(root / "operator-manual.env")
    ]


def test_export_direct_delivery_child_with_spaces_is_forwarded(launcher):
    output = launcher.root / "delivery" / "candidate export.txt"
    result = launcher.run("export", "--key-id", "1", "--output", output, "--operation-id", OP)
    assert result.returncode == 0, result.stderr
    assert values(cli_arguments(launcher.calls()[0]), "--output") == [str(output)]


@pytest.mark.parametrize(
    "relative",
    [
        "outside.txt",
        "ciphertext/export.txt",
        "delivery/nested/export.txt",
        "delivery/../audit/export.txt",
    ],
)
def test_export_rejects_non_delivery_direct_child(launcher, relative):
    no_docker(
        launcher, launcher.run("export", "--key-id", "1", "--output", launcher.root / relative)
    )


def test_export_existing_file_or_dangling_symlink_is_not_overwritten(launcher):
    output = launcher.root / "delivery" / "existing.txt"
    output.write_text("synthetic existing material")
    output.chmod(0o600)
    no_docker(launcher, launcher.run("export", "--key-id", "1", "--output", output))
    assert output.read_text() == "synthetic existing material"
    output.unlink()
    output.symlink_to(launcher.root / "absent")
    no_docker(launcher, launcher.run("export", "--key-id", "1", "--output", output))


@pytest.mark.parametrize("updates", [{"DOCKER_CONTEXT": "remote"}, {"DOCKER_HOST": "ssh://remote"}])
def test_remote_docker_environment_is_rejected(launcher, updates):
    no_docker(launcher, launcher.run("status", updates=updates))


def test_explicit_local_docker_environment_is_supported(launcher):
    result = launcher.run(
        "status",
        updates={"DOCKER_CONTEXT": "default", "DOCKER_HOST": "unix:///var/run/docker.sock"},
    )
    assert result.returncode == 0, result.stderr
    assert len(launcher.calls()) == 1
    assert launcher.calls()[0]["argv"][:3] == ["--context", "default", "run"]


@pytest.mark.parametrize("tool", ["sync", "mktemp"])
def test_audit_intent_failure_prevents_docker(launcher, tool):
    result = launcher.run("status", updates={f"BASH_FUNC_{tool}%%": "() { return 1; }"})
    no_docker(launcher, result)


@pytest.mark.parametrize("name", ["operator-manual.env", "master.key", "operator-image.id"])
def test_hardlinked_private_file_prevents_docker(launcher, tmp_path, name):
    os.link(launcher.root / name, tmp_path / "untrusted-alias")
    no_docker(launcher, launcher.run("status"))


@pytest.mark.parametrize("signum,exit_code", [(signal.SIGTERM, 143), (signal.SIGINT, 130)])
def test_interrupt_requires_reconciliation_without_retry(launcher, signum, exit_code):
    env = {**launcher.env, "FAKE_DOCKER_SLEEP": "10"}
    process = subprocess.Popen(
        [BASH, str(LAUNCHER), "status", "--operation-id", OP],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 5
        while not launcher.calls():
            if process.poll() is not None or time.monotonic() >= deadline:
                pytest.fail("Fake Docker did not start")
            time.sleep(0.01)
        process.send_signal(signum)
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == exit_code
        assert OP in stderr and "RECONCILE_REQUIRED" in stderr
        assert CANARY not in stdout + stderr
        assert len(launcher.calls()) == 1
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)
