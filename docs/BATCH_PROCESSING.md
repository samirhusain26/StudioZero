# Batch Processing & Automation Guide

StudioZero includes a robust batch processing system that orchestrates video generation from a Google Sheet queue. This document details the setup and usage of the automation layer.

---

## 1. Google Sheets Setup

The `src/batch_runner.py` polls a Google Sheet for new jobs. Your sheet must include the following column headers (order doesn't matter, but names must match):

| Column | Purpose |
|--------|---------|
| `movie_title` | The movie name, theme, or project title. |
| `Job_Type` | `Movie` (default) or `Animated` for episodic parodies. |
| `Status` | Jobs are processed if `Status` is `Pending`. |
| `video_link` | Automatically populated with the Google Drive link on success. |
| `log_link` | Automatically populated with the pipeline JSON log link. |
| `icloud_link` | Populated with the local macOS iCloud path (if available). |
| `caption` | Automatically populated with a generated social media caption. |
| `notes` | Populated with detailed error messages on failure. |
| `start_time` | Timestamp when processing began. |
| `end_time` | Timestamp when processing completed. |

---

## 2. Cloud Configuration

To enable batch processing, you must configure Google Cloud credentials:

1. **Service Account:** Create a [Google service account](https://console.cloud.google.com/iam-admin/serviceaccounts) with the **Google Drive** and **Google Sheets** APIs enabled.
2. **Credentials:** Download the JSON credentials file and save it to `assets/creds/drive_credentials.json`.
3. **Sharing:** Share your Google Sheet and the destination Drive folders with the service account's email address.
4. **Environment:** Update your `.env` file:
   ```bash
   DRIVE_APPLICATION_CREDENTIALS=assets/creds/drive_credentials.json
   BATCH_SHEET_URL=https://docs.google.com/spreadsheets/d/your_sheet_id
   DRIVE_VIDEO_FOLDER_ID=your_video_folder_id
   DRIVE_LOGS_FOLDER_ID=your_logs_folder_id
   ```

---

## 3. Usage

Run the batch runner from the command line:

```bash
# Process all pending jobs in the sheet
python -m src.batch_runner

# Limit to a specific number of jobs
python -m src.batch_runner --limit 5

# Enable verbose logging
python -m src.batch_runner --verbose
```

The runner will:
1. Mark a row as `Processing`.
2. Orchestrate the appropriate pipeline (Movie or Animated).
3. Upload the resulting video and logs to Google Drive.
4. Generate a social media caption via `src/marketing.py`.
5. Update the sheet with links and timestamps.

---

## 4. macOS Automation

You can automate batch processing on macOS using a shell script triggered by **cron** or **Shortcuts.app**.

### Automation Script Example
Create a script at `scripts/run_batch.sh`:

```bash
#!/bin/bash
PROJECT_DIR="/Users/yourname/StudioZero"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
LOG_FILE="$PROJECT_DIR/output/batch_run_log.txt"

{
    echo "--- Batch Run Started: $(date) ---"
    cd "$PROJECT_DIR" || exit 1
    "$PYTHON_BIN" -m src.batch_runner --limit 1
    echo "--- Batch Run Finished: $(date) ---"
} >> "$LOG_FILE" 2>&1
```

### Scheduling with Crontab
To run the batch processor every hour:

```bash
crontab -e
# Add the following line:
0 * * * * /Users/yourname/StudioZero/scripts/run_batch.sh
```
