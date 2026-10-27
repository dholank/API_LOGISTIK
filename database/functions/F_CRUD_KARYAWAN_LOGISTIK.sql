-- Fresh-only: apply manually only after confirming this function is absent.
-- Invoke through bound PL/SQL, not SELECT; Python owns the transaction.
CREATE FUNCTION F_CRUD_KARYAWAN_LOGISTIK (
    P_MODE IN VARCHAR2,
    P_ID_KARYAWAN IN NUMBER,
    P_NAMA IN VARCHAR2 DEFAULT NULL,
    P_CABANG IN VARCHAR2 DEFAULT NULL,
    P_NO_TELP IN VARCHAR2 DEFAULT NULL,
    P_STATUS IN VARCHAR2 DEFAULT NULL
) RETURN CLOB
IS
    V_MODE VARCHAR2(32767);
    V_NAMA VARCHAR2(32767);
    V_CABANG VARCHAR2(32767);
    V_NO_TELP VARCHAR2(32767);
    V_STATUS VARCHAR2(32767);
    V_DATA CLOB;
    V_MESSAGE VARCHAR2(100);

    FUNCTION MAKE_RESPONSE (
        P_CODE IN VARCHAR2,
        P_MESSAGE IN VARCHAR2,
        P_DATA IN CLOB DEFAULT NULL
    ) RETURN CLOB
    IS
        V_RESPONSE CLOB;
    BEGIN
        SELECT JSON_OBJECT(
            'success' VALUE CASE WHEN P_CODE = 'SUCCESS' THEN 'true' ELSE 'false' END
                FORMAT JSON,
            'code' VALUE P_CODE,
            'message' VALUE P_MESSAGE,
            'data' VALUE CASE WHEN P_CODE = 'SUCCESS' THEN P_DATA ELSE NULL END
                FORMAT JSON
            NULL ON NULL RETURNING CLOB STRICT
        ) INTO V_RESPONSE FROM DUAL;
        RETURN V_RESPONSE;
    END MAKE_RESPONSE;

    FUNCTION MAKE_KARYAWAN_DATA RETURN CLOB
    IS
        V_KARYAWAN CLOB;
    BEGIN
        SELECT JSON_OBJECT(
            'id_karyawan' VALUE TO_CHAR(P_ID_KARYAWAN, 'FM99990',
                'NLS_NUMERIC_CHARACTERS=''.,'''),
            'nama' VALUE V_NAMA,
            'cabang' VALUE V_CABANG,
            'no_telp' VALUE V_NO_TELP,
            'status' VALUE V_STATUS
            NULL ON NULL RETURNING CLOB STRICT
        ) INTO V_KARYAWAN FROM DUAL;
        RETURN V_KARYAWAN;
    END MAKE_KARYAWAN_DATA;
BEGIN
    V_MODE := UPPER(TRIM(P_MODE));
    IF V_MODE IS NULL OR V_MODE NOT IN ('CREATE', 'READ', 'UPDATE', 'DELETE') THEN
        RETURN MAKE_RESPONSE('KRY_004', 'Mode operasi tidak valid');
    END IF;

    IF P_ID_KARYAWAN IS NULL THEN
        RETURN MAKE_RESPONSE('KRY_002', 'ID karyawan wajib diisi');
    END IF;
    -- Validate the unconstrained NUMBER before NUMBER(5) can round a fraction.
    IF P_ID_KARYAWAN < 0 OR P_ID_KARYAWAN > 99999
        OR P_ID_KARYAWAN <> TRUNC(P_ID_KARYAWAN) THEN
        RETURN MAKE_RESPONSE('KRY_003', 'ID karyawan harus bilangan bulat 0 sampai 99999');
    END IF;

    IF V_MODE IN ('CREATE', 'UPDATE') THEN
        V_NAMA := TRIM(P_NAMA);
        V_CABANG := TRIM(P_CABANG);
        V_NO_TELP := P_NO_TELP;
        V_STATUS := TRIM(P_STATUS);

        IF V_NAMA IS NULL OR NOT REGEXP_LIKE(V_NAMA, '[^[:space:]]') THEN
            RETURN MAKE_RESPONSE('KRY_005', 'Nama wajib diisi');
        END IF;
        IF LENGTHB(V_NAMA) > 50 THEN
            RETURN MAKE_RESPONSE('KRY_006', 'Nama melebihi 50 byte');
        END IF;
        IF V_CABANG IS NULL OR NOT REGEXP_LIKE(V_CABANG, '[^[:space:]]') THEN
            RETURN MAKE_RESPONSE('KRY_007', 'Cabang wajib diisi');
        END IF;
        IF LENGTHB(V_CABANG) > 30 THEN
            RETURN MAKE_RESPONSE('KRY_008', 'Cabang melebihi 30 byte');
        END IF;
        IF V_NO_TELP IS NULL OR NOT REGEXP_LIKE(V_NO_TELP, '[^[:space:]]') THEN
            RETURN MAKE_RESPONSE('KRY_009', 'Nomor telepon wajib diisi');
        END IF;
        IF LENGTHB(V_NO_TELP) > 20 THEN
            RETURN MAKE_RESPONSE('KRY_010', 'Nomor telepon melebihi 20 byte');
        END IF;
        IF TRANSLATE(V_NO_TELP, 'x0123456789', 'x') IS NOT NULL THEN
            RETURN MAKE_RESPONSE('KRY_011', 'Nomor telepon hanya boleh berisi digit ASCII');
        END IF;
        IF V_STATUS IS NULL OR NOT REGEXP_LIKE(V_STATUS, '[^[:space:]]') THEN
            RETURN MAKE_RESPONSE('KRY_012', 'Status wajib diisi');
        END IF;
        IF LENGTHB(V_STATUS) > 10 THEN
            RETURN MAKE_RESPONSE('KRY_013', 'Status melebihi 10 byte');
        END IF;
    END IF;

    CASE V_MODE
        WHEN 'CREATE' THEN
            BEGIN
                INSERT INTO KARYAWAN (ID_KARYAWAN, NAMA, CABANG, NO_TELP, STATUS)
                VALUES (P_ID_KARYAWAN, V_NAMA, V_CABANG, V_NO_TELP, V_STATUS);
            EXCEPTION
                WHEN DUP_VAL_ON_INDEX THEN
                    RETURN MAKE_RESPONSE('KRY_001', 'ID karyawan sudah terdaftar');
            END;
            V_MESSAGE := 'Data karyawan berhasil ditambahkan';
        WHEN 'READ' THEN
            BEGIN
                SELECT NAMA, CABANG, NO_TELP, STATUS
                INTO V_NAMA, V_CABANG, V_NO_TELP, V_STATUS
                FROM KARYAWAN
                WHERE ID_KARYAWAN = P_ID_KARYAWAN;
            EXCEPTION
                WHEN NO_DATA_FOUND THEN
                    RETURN MAKE_RESPONSE('KRY_404', 'Data karyawan tidak ditemukan');
            END;
            V_MESSAGE := 'Data karyawan berhasil ditemukan';
        WHEN 'UPDATE' THEN
            UPDATE KARYAWAN
            SET NAMA = V_NAMA, CABANG = V_CABANG, NO_TELP = V_NO_TELP, STATUS = V_STATUS
            WHERE ID_KARYAWAN = P_ID_KARYAWAN;
            IF SQL%ROWCOUNT = 0 THEN
                RETURN MAKE_RESPONSE('KRY_404', 'Data karyawan tidak ditemukan');
            END IF;
            V_MESSAGE := 'Data karyawan berhasil diperbarui';
        WHEN 'DELETE' THEN
            DELETE FROM KARYAWAN WHERE ID_KARYAWAN = P_ID_KARYAWAN;
            IF SQL%ROWCOUNT = 0 THEN
                RETURN MAKE_RESPONSE('KRY_404', 'Data karyawan tidak ditemukan');
            END IF;
            V_MESSAGE := 'Data karyawan berhasil dihapus';
    END CASE;

    V_DATA := MAKE_KARYAWAN_DATA;
    RETURN MAKE_RESPONSE('SUCCESS', V_MESSAGE, V_DATA);
EXCEPTION
    -- A failure after DML also requires Python to roll back the entire call.
    WHEN OTHERS THEN
        RETURN MAKE_RESPONSE('KRY_999', 'Operasi karyawan gagal diproses');
END F_CRUD_KARYAWAN_LOGISTIK;
/
