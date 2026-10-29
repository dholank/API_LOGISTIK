#!/usr/bin/env bash
set +x
set -euo pipefail
umask 077

fail() {
    printf '%s\n' "$1" >&2
    exit "${2:-1}"
}

if [[ ${1:-} == --help && $# == 1 ]]; then
    printf '%s\n' \
        'Usage: scripts/api_key_operator.sh COMMAND [CLI OPTIONS]' \
        'Commands: status prepare export confirm-distributed activate revoke reconcile' \
        'Private root: API_LOGISTIK_OPERATOR_ROOT or ${XDG_DATA_HOME:-$HOME/.local/share}/api-logistik' \
        'Requires operator-manual.env, operator-image.id, master.key, ciphertext/, delivery/, audit/.' \
        'Use explicit ID/VERSION/reason. Reconcile requires the original --operation-id.' \
        'No scheduler, implicit activation, or retry. Never pass raw keys or credentials.'
    exit 0
fi

[[ $# -gt 0 ]] || fail INVALID_COMMAND 2
command_name=$1
shift
case "$command_name" in
    status|prepare|export|confirm-distributed|activate|revoke|reconcile) ;;
    *) fail INVALID_COMMAND 2 ;;
esac

declare -A seen=()
forwarded=()
operation_id=
output=
while (( $# )); do
    token=$1
    option=${token%%=*}
    case "$command_name:$option" in
        *:--operation-id|prepare:--expected-version|confirm-distributed:--expected-version|activate:--expected-version|revoke:--expected-version|confirm-distributed:--key-id|export:--key-id|revoke:--key-id|reconcile:--key-id|prepare:--reason|confirm-distributed:--reason|activate:--reason|revoke:--reason|export:--output)
            [[ ! ${seen[$option]+present} ]] || fail DUPLICATE_OPTION 2
            if [[ $token == *=* ]]; then
                value=${token#*=}
                tokens=("$token")
            else
                [[ $# -ge 2 ]] || fail INVALID_ARGUMENTS 2
                value=$2
                tokens=("$token" "$value")
                shift
            fi
            [[ -n $value ]] || fail INVALID_ARGUMENTS 2
            case "$option" in
                --operation-id)
                    [[ $value =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || fail INVALID_OPERATION_ID 2
                    operation_id=$value
                    ;;
                --expected-version)
                    [[ $value =~ ^[0-9]+$ ]] || fail INVALID_VERSION 2
                    ;;
                --key-id)
                    [[ $value =~ ^[0-9]+$ && $value == *[1-9]* ]] || fail INVALID_KEY_ID 2
                    ;;
                --reason)
                    case "$value" in
                        bootstrap|scheduled|manual_rotation|suspected_compromise|distribution_confirmed|key_retired|recovery) ;;
                        *) fail INVALID_REASON 2 ;;
                    esac
                    ;;
                --output) output=$value ;;
            esac
            seen[$option]=1
            [[ $option == --operation-id ]] || forwarded+=("${tokens[@]}")
            ;;
        prepare:--replace-pending|prepare:--emergency|activate:--manual|activate:--emergency)
            [[ $token == "$option" && ! ${seen[$option]+present} ]] || fail INVALID_ARGUMENTS 2
            seen[$option]=1
            forwarded+=("$token")
            ;;
        *) fail INVALID_ARGUMENTS 2 ;;
    esac
    shift
done

required=()
case "$command_name" in
    prepare|activate) required=(--expected-version --reason) ;;
    confirm-distributed|revoke) required=(--key-id --expected-version --reason) ;;
    export) required=(--key-id --output) ;;
    reconcile) required=(--operation-id) ;;
esac
for option in "${required[@]}"; do
    [[ ${seen[$option]+present} ]] || fail MISSING_REQUIRED_OPTION 2
done
[[ ! ${seen[--manual]+present} || ! ${seen[--emergency]+present} ]] || fail INVALID_ARGUMENTS 2

[[ ${OSTYPE:-} == linux* ]] || fail LINUX_REQUIRED
uid=$(id -u)
gid=$(id -g)
[[ $uid != 0 ]] || fail NON_ROOT_OPERATOR_REQUIRED
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
root=${API_LOGISTIK_OPERATOR_ROOT:-${XDG_DATA_HOME:-$HOME/.local/share}/api-logistik}
root=${root%/}
[[ $root == /* && $root != / && $root != *$'\n'* && $root != *$'\r'* && $root != *,* && $root != *:* && $root != *\"* ]] || fail INVALID_PRIVATE_ROOT
[[ $root != "$project" && $root != "$project/"* ]] || fail PRIVATE_ROOT_INSIDE_PROJECT

check_ancestor() {
    local path=$1 owner permissions mode
    [[ -d $path && ! -L $path ]] || fail UNSAFE_PRIVATE_PATH
    read -r owner permissions < <(stat -c '%u %a' -- "$path")
    [[ $owner == 0 || $owner == "$uid" ]] || fail UNSAFE_PRIVATE_OWNER
    mode=$((8#$permissions))
    if (( mode & 0022 )); then
        [[ $owner == 0 ]] && (( mode & 01000 )) || fail UNSAFE_PRIVATE_ANCESTOR
    fi
    [[ ! -e $path/.git && ! -e $path/pyproject.toml ]] || fail PRIVATE_ROOT_INSIDE_PROJECT
}
check_ancestor /
current=
IFS=/ read -r -a components <<< "$root"
for part in "${components[@]}"; do
    [[ -n $part ]] || continue
    [[ $part != . && $part != .. ]] || fail UNSAFE_PRIVATE_PATH
    current+=/$part
    check_ancestor "$current"
done
[[ $(realpath -e -- "$root") == "$root" ]] || fail UNSAFE_PRIVATE_PATH

private_directory() {
    [[ -d $1 && ! -L $1 ]] || fail PRIVATE_DIRECTORY_REQUIRED
    [[ $(stat -c '%u:%a' -- "$1") == "$uid:700" ]] || fail UNSAFE_DIRECTORY_PERMISSION
}
private_file() {
    [[ -f $1 && ! -L $1 ]] || fail PRIVATE_FILE_REQUIRED
    [[ $(stat -c '%u:%a:%h' -- "$1") == "$uid:600:1" ]] || fail UNSAFE_FILE_PERMISSION
}
private_directory "$root"
for directory in ciphertext delivery audit; do
    private_directory "$root/$directory"
done
for file in operator-manual.env master.key operator-image.id; do
    private_file "$root/$file"
done
size=$(stat -c '%s' -- "$root/operator-image.id")
[[ $size == 71 || $size == 72 ]] || fail INVALID_IMAGE_PIN
IFS= read -r image < "$root/operator-image.id" || [[ -n ${image:-} ]]
[[ $image =~ ^sha256:[0-9a-f]{64}$ ]] || fail INVALID_IMAGE_PIN

if [[ $command_name == export ]]; then
    [[ $output == /* && ${output%/*} == "$root/delivery" && ${output##*/} != . && ${output##*/} != .. && -n ${output##*/} ]] || fail INVALID_EXPORT_DESTINATION 2
    [[ $output != *$'\n'* && $output != *$'\r'* && ! -e $output && ! -L $output ]] || fail EXPORT_DESTINATION_EXISTS 2
fi
command -v docker >/dev/null 2>&1 || fail DOCKER_UNAVAILABLE
[[ -z ${DOCKER_CONTEXT:-} || ${DOCKER_CONTEXT:-} == default ]] || fail LOCAL_DOCKER_CONTEXT_REQUIRED
[[ -z ${DOCKER_HOST:-} || ${DOCKER_HOST:-} == unix:///var/run/docker.sock ]] || fail LOCAL_DOCKER_HOST_REQUIRED
if [[ -z $operation_id ]]; then
    IFS= read -r operation_id < /proc/sys/kernel/random/uuid
fi
[[ $operation_id =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || fail INVALID_OPERATION_ID

audit=$(mktemp -- "$root/audit/$command_name-$operation_id-XXXXXX.log")
printf 'intent operation_id=%s command=%s image_id=%s started_at=%s\n' \
    "$operation_id" "$command_name" "$image" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$audit"
sync -f -- "$audit" "$root/audit" || fail AUDIT_INTENT_NOT_DURABLE

interrupted=0
docker_pid=
on_interrupt() {
    interrupted=$1
    if [[ -n $docker_pid ]]; then
        kill -TERM "$docker_pid" 2>/dev/null || true
    else
        printf 'RECONCILE_REQUIRED operation_id=%s; execution interrupted\n' "$operation_id" >&2
        exit "$interrupted"
    fi
}
trap 'on_interrupt 130' INT
trap 'on_interrupt 143' TERM

exec {output_fd}> >(tee -a -- "$audit")
tee_pid=$!
docker --context default run --rm --pull never --user "$uid:$gid" --read-only \
    --tmpfs /tmp:rw,noexec,nosuid,size=128m \
    --cap-drop ALL --security-opt no-new-privileges \
    --env USER=local-operator \
    --mount "type=bind,source=$root,target=$root,readonly" \
    --mount "type=bind,source=$root/ciphertext,target=$root/ciphertext" \
    --mount "type=bind,source=$root/delivery,target=$root/delivery" \
    "$image" api-logistik-keys --env-file "$root/operator-manual.env" \
    --operation-id "$operation_id" "$command_name" "${forwarded[@]}" \
    >&"$output_fd" 2>/dev/null &
docker_pid=$!
if wait "$docker_pid"; then
    result=0
else
    result=$?
fi
if (( interrupted )); then
    wait "$docker_pid" 2>/dev/null || true
    result=$interrupted
fi
docker_pid=
exec {output_fd}>&-
if ! wait "$tee_pid"; then
    printf 'AUDIT_OUTPUT_FAILED operation_id=%s; review before further mutation\n' "$operation_id" >&2
fi
trap - INT TERM
printf 'completed operation_id=%s exit_code=%s finished_at=%s\n' \
    "$operation_id" "$result" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$audit" || true
if ! sync -f -- "$audit" "$root/audit"; then
    printf 'AUDIT_SYNC_FAILED operation_id=%s; review before further mutation\n' "$operation_id" >&2
fi
case "$result" in
    4|130|143) printf 'RECONCILE_REQUIRED operation_id=%s; do not retry mutation\n' "$operation_id" >&2 ;;
    125|126|127) printf 'DOCKER_EXECUTION_FAILED operation_id=%s\n' "$operation_id" >&2 ;;
esac
exit "$result"
