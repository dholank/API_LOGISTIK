-- Development/training only; verify schema, free fixture IDs and CRUD function first.
-- Use a dedicated session with autocommit OFF; review results before committing manually.
DECLARE
    V_RESPONSE CLOB;
    V_RESULT JSON_OBJECT_T;
    V_DATA JSON_OBJECT_T;
    V_SUCCESS BOOLEAN;
    V_CODE VARCHAR2(32);
    V_RESULT_ID VARCHAR2(5);
    V_ID NUMBER;
    V_SUFFIX VARCHAR2(2);
BEGIN
    SAVEPOINT SP_DUMMY_KARYAWAN;

    FOR I IN 1..10 LOOP
        V_ID := 90000 + I;
        V_SUFFIX := TO_CHAR(I, 'FM00');
        V_RESPONSE := F_CRUD_KARYAWAN_LOGISTIK(
            P_MODE => 'CREATE',
            P_ID_KARYAWAN => V_ID,
            P_NAMA => 'DUMMY KARYAWAN ' || V_SUFFIX,
            P_CABANG => 'TRAINING',
            P_NO_TELP => '00000000' || V_SUFFIX,
            P_STATUS => 'AKTIF'
        );

        V_RESULT := JSON_OBJECT_T.PARSE(V_RESPONSE);
        V_RESULT.ON_ERROR(1);
        V_SUCCESS := V_RESULT.GET_BOOLEAN('success');
        V_CODE := V_RESULT.GET_STRING('code');
        IF V_SUCCESS IS NULL OR NOT V_SUCCESS OR V_CODE IS NULL OR V_CODE <> 'SUCCESS' THEN
            RAISE_APPLICATION_ERROR(-20001, 'Dummy karyawan gagal; seluruh penambahan dibatalkan.');
        END IF;

        V_DATA := V_RESULT.GET_OBJECT('data');
        IF V_DATA IS NULL THEN
            RAISE_APPLICATION_ERROR(-20002, 'Respons dummy karyawan tidak sesuai kontrak.');
        END IF;
        V_DATA.ON_ERROR(1);
        V_RESULT_ID := V_DATA.GET_STRING('id_karyawan');
        IF V_RESULT_ID IS NULL OR V_RESULT_ID <> TO_CHAR(V_ID, 'FM99990') THEN
            RAISE_APPLICATION_ERROR(-20002, 'Respons dummy karyawan tidak sesuai kontrak.');
        END IF;
    END LOOP;
EXCEPTION
    WHEN OTHERS THEN
        -- Business errors can follow DML; discard every row from this invocation.
        ROLLBACK TO SP_DUMMY_KARYAWAN;
        RAISE;
END;
/
