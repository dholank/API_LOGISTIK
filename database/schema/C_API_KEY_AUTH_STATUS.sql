-- Conditional legacy patch: first verify this named constraint and stop every legacy writer.
-- Use a dedicated maintenance session with stop-on-error enabled; DDL cannot be rolled back.
ALTER TABLE API_KEY_AUTH
    DROP CONSTRAINT CK_API_KEY_AUTH_STATUS;

ALTER TABLE API_KEY_AUTH
    ADD CONSTRAINT CK_API_KEY_AUTH_STATUS
    CHECK (STATUS IN ('PENDING', 'ACTIVE', 'GRACE', 'EXPIRED', 'REVOKED'))
    ENABLE VALIDATE;
