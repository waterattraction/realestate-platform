-- Phase 3: followup attachments
CREATE TABLE IF NOT EXISTS trust_overdue_followup_attachments (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entry_id            BIGINT NOT NULL REFERENCES trust_overdue_followup_entries (id) ON DELETE CASCADE,
    file_name           VARCHAR(500) NOT NULL,
    stored_path         VARCHAR(1000) NOT NULL,
    content_type        VARCHAR(128),
    file_size           BIGINT,
    attachment_type     VARCHAR(16) NOT NULL DEFAULT 'file',
    uploaded_by         VARCHAR(64),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_followup_attachment_type CHECK (attachment_type IN ('image', 'file'))
);

CREATE INDEX IF NOT EXISTS idx_followup_attachments_entry
    ON trust_overdue_followup_attachments (entry_id);
