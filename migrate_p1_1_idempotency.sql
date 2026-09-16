/* P1.1 - Idempotencia de lecturas OEM. Migracion aditiva y transaccional. */

SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID('dbo.horometer_updates', 'U') IS NULL
    BEGIN
        THROW 51000, 'No existe dbo.horometer_updates.', 1;
    END;

    IF COL_LENGTH('dbo.horometer_updates', 'idempotency_key') IS NULL
        ALTER TABLE dbo.horometer_updates ADD idempotency_key VARCHAR(128) NULL;

    IF COL_LENGTH('dbo.horometer_updates', 'source_reading_datetime') IS NULL
        ALTER TABLE dbo.horometer_updates ADD source_reading_datetime DATETIMEOFFSET(7) NULL;

    IF COL_LENGTH('dbo.horometer_updates', 'source_value') IS NULL
        ALTER TABLE dbo.horometer_updates ADD source_value DECIMAL(18, 2) NULL;

    IF COL_LENGTH('dbo.horometer_updates', 'decision') IS NULL
        ALTER TABLE dbo.horometer_updates ADD decision VARCHAR(50) NULL;

    IF COL_LENGTH('dbo.horometer_updates', 'write_status') IS NULL
        ALTER TABLE dbo.horometer_updates ADD write_status VARCHAR(50) NULL;

    IF COL_LENGTH('dbo.horometer_updates', 'http_status') IS NULL
        ALTER TABLE dbo.horometer_updates ADD http_status INT NULL;

    IF COL_LENGTH('dbo.horometer_updates', 'fracttal_reading_id') IS NULL
        ALTER TABLE dbo.horometer_updates ADD fracttal_reading_id BIGINT NULL;

    IF COL_LENGTH('dbo.horometer_updates', 'fracttal_is_duplicate') IS NULL
        ALTER TABLE dbo.horometer_updates ADD fracttal_is_duplicate BIT NULL;

    IF COL_LENGTH('dbo.horometer_updates', 'verification_value') IS NULL
        ALTER TABLE dbo.horometer_updates ADD verification_value DECIMAL(18, 2) NULL;

    IF COL_LENGTH('dbo.horometer_updates', 'verification_status') IS NULL
        ALTER TABLE dbo.horometer_updates ADD verification_status VARCHAR(50) NULL;

    IF COL_LENGTH('dbo.horometer_updates', 'error_code') IS NULL
        ALTER TABLE dbo.horometer_updates ADD error_code VARCHAR(100) NULL;

    IF COL_LENGTH('dbo.horometer_updates', 'attempt_count') IS NULL
        ALTER TABLE dbo.horometer_updates ADD attempt_count INT NOT NULL
            CONSTRAINT DF_horometer_updates_attempt_count DEFAULT 0;

    IF COL_LENGTH('dbo.horometer_updates', 'last_attempt_at') IS NULL
        ALTER TABLE dbo.horometer_updates ADD last_attempt_at DATETIMEOFFSET(7) NULL;

    DECLARE @duplicate_count INT;
    DECLARE @duplicate_sql NVARCHAR(MAX) = N'
        SELECT @count = COUNT(*)
        FROM
        (
            SELECT idempotency_key
            FROM dbo.horometer_updates
            WHERE idempotency_key IS NOT NULL
            GROUP BY idempotency_key
            HAVING COUNT(*) > 1
        ) AS duplicates;';

    EXEC sys.sp_executesql
        @duplicate_sql,
        N'@count INT OUTPUT',
        @count = @duplicate_count OUTPUT;

    IF @duplicate_count > 0
    BEGIN
        THROW 51001, 'Existen idempotency_key duplicadas; no se creara el indice.', 1;
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.indexes
        WHERE name = 'UX_horometer_updates_idempotency_key'
          AND object_id = OBJECT_ID('dbo.horometer_updates')
    )
    BEGIN
        EXEC sys.sp_executesql N'
            CREATE UNIQUE INDEX UX_horometer_updates_idempotency_key
            ON dbo.horometer_updates(idempotency_key)
            WHERE idempotency_key IS NOT NULL;';
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
