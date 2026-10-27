import pytest


@pytest.mark.parametrize(
    "identifier", ["", "123456", "１２", "١٢", "+1", "-1", "1.0", " 1", "1 ", 1, True, None]
)
def test_create_id_requires_one_to_five_ascii_digit_string(harness, body, identifier):
    body["id_karyawan"] = identifier
    response = harness.client.post(
        "/api/v1/karyawan", json=body, headers={"X-API-Key": harness.key}
    )
    assert response.status_code == 422
    assert harness.business_calls == []
    assert "commit" not in harness.events


@pytest.mark.parametrize("identifier", ["123456", "１２", "١٢", "+1", "-1", "1.0"])
def test_path_id_rejects_non_ascii_or_out_of_bounds(harness, identifier):
    response = harness.client.get(
        f"/api/v1/karyawan/{identifier}", headers={"X-API-Key": harness.key}
    )
    assert response.status_code == 422
    assert harness.business_calls == []


@pytest.mark.parametrize("phone", ["", "0" * 21, "１２", "١٢", "+123", "1 2", 123, True])
def test_phone_rejects_non_ascii_non_string_and_length(harness, body, phone):
    body["no_telp"] = phone
    response = harness.client.post(
        "/api/v1/karyawan", json=body, headers={"X-API-Key": harness.key}
    )
    assert response.status_code == 422
    assert harness.business_calls == []


@pytest.mark.parametrize("phone", ["0", "0" * 20])
def test_phone_preserves_leading_zero_at_both_length_bounds(harness, body, phone):
    body["no_telp"] = phone
    response = harness.client.post(
        "/api/v1/karyawan", json=body, headers={"X-API-Key": harness.key}
    )
    assert response.status_code == 201
    assert harness.business_calls[0][2]["no_telp"] == phone


@pytest.mark.parametrize("field,limit", [("nama", 50), ("cabang", 30), ("status", 10)])
@pytest.mark.parametrize("overflow", [False, True])
def test_text_limits_are_utf8_bytes(harness, body, field, limit, overflow):
    body[field] = "é" * (limit // 2) + ("a" if overflow else "")
    response = harness.client.post(
        "/api/v1/karyawan", json=body, headers={"X-API-Key": harness.key}
    )
    assert response.status_code == (422 if overflow else 201)
    assert bool(harness.business_calls) is not overflow


@pytest.mark.parametrize(
    "method,path", [("POST", "/api/v1/karyawan"), ("PUT", "/api/v1/karyawan/1")]
)
def test_unknown_body_fields_are_rejected(harness, body, method, path):
    if method == "PUT":
        body.pop("id_karyawan")
    body["unknown"] = "private-body-marker"
    response = harness.client.request(method, path, json=body, headers={"X-API-Key": harness.key})
    assert response.status_code == 422
    assert "private-body-marker" not in response.text
    assert harness.business_calls == []


@pytest.mark.parametrize("field", ["nama", "cabang", "no_telp", "status"])
def test_put_requires_every_mutable_field(harness, body, field):
    body.pop("id_karyawan")
    body.pop(field)
    response = harness.client.put(
        "/api/v1/karyawan/1", json=body, headers={"X-API-Key": harness.key}
    )
    assert response.status_code == 422
    assert harness.business_calls == []


def test_put_rejects_identifier_in_body(harness, body):
    response = harness.client.put(
        "/api/v1/karyawan/1", json=body, headers={"X-API-Key": harness.key}
    )
    assert response.status_code == 422
    assert harness.business_calls == []
