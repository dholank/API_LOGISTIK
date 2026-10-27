-- Dedicated setup session only: COMMIT also commits unrelated pending work in this session.
-- Existing pointers, readiness, version and rotation dates are never overwritten.
MERGE INTO API_KEY_ROTATION_STATE target
USING (SELECT 'GLOBAL' AS SCOPE_ID FROM DUAL) source
ON (target.SCOPE_ID = source.SCOPE_ID)
WHEN NOT MATCHED THEN
    INSERT (SCOPE_ID, VERSION)
    VALUES (source.SCOPE_ID, 0);

COMMIT;
