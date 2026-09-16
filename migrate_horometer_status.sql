SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'dbo.horometer_updates', N'U') IS NULL
        THROW 51010, 'No existe dbo.horometer_updates.', 1;

    IF EXISTS
    (
        SELECT 1
        FROM sys.check_constraints
        WHERE name = N'CK_horometer_updates_status'
          AND parent_object_id = OBJECT_ID(N'dbo.horometer_updates')
    )
    BEGIN
        ALTER TABLE dbo.horometer_updates
            DROP CONSTRAINT CK_horometer_updates_status;
    END;

    ALTER TABLE dbo.horometer_updates
        ADD CONSTRAINT CK_horometer_updates_status CHECK
        (
            [status] IN
            (
                'ERROR',
                'METER_NOT_FOUND',
                'NOT_FOUND',
                'REJECTED',
                'SKIPPED',
                'UPDATED',
                'WOULD_UPDATE',
                'RECEIVED',
                'METER_SERIAL_MISMATCH',
                'REVIEW',
                'NO_VALID_METER',
                'SKIP_EQUAL',
                'REVIEW_INCONSISTENCY',
                'INTENT_RECORDED',
                'WRITE_IN_PROGRESS',
                'VERIFIED',
                'WRITE_AMBIGUOUS',
                'ERROR_RETRYABLE'
            )
        );

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
