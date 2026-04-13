# Batch Processing & Automation Guide

StudioZero includes a robust batch processing system designed for high-volume automated production from a Google Sheet. This is accessible via the **Stock Footage -> Sheet Automated** route in the CLI.

---

## 1. Google Sheet Setup

To automate production, you must maintain a Google Sheet with the following columns (headers must be in the first row):

| Column | Description |
| :--- | :--- |
| **Movie_Name** | The title of the movie or story idea to recap. |
| **Status** | Must be `Pending` for the batch runner to pick it up. |
| **Video_Link** | (Output) Populated with the Google Drive link after rendering. |
| **Social_Caption** | (Output) Auto-generated marketing copy. |
| **Timestamp** | (Output) When the job was completed. |

---

## 2. Configuration

1.  **Service Account**: Place your Google Cloud service account JSON in `assets/creds/google_creds.json`.
2.  **Environment**: Ensure `SHEET_ID` and `DRIVE_FOLDER_ID` are set in your `.env` file.
3.  **Permissions**: Share your Google Sheet and the target Google Drive folder with the service account email.

---

## 3. Execution

### Via CLI Wizard (Recommended)
1.  Run `python -m src.app`.
2.  Choose **1** (Stock Footage).
3.  Choose **1** (Sheet Automated).

The runner will begin processing all rows where `Status` is `Pending`.

### Direct Execution
You can also run the batch processor directly without the wizard:
```bash
python -m src.batch_runner
```

---

## 4. Automation & Scheduling

For truly hands-free operation, you can schedule the batch runner using `crontab` (Linux/macOS) or Task Scheduler (Windows).

### macOS Example (run every hour):
1.  Open terminal and type `crontab -e`.
2.  Add the following line (replace with your actual paths):
```bash
0 * * * * cd /path/to/StudioZero && /path/to/venv/bin/python -m src.batch_runner >> output/pipeline_logs/batch.log 2>&1
```

---

## 5. Monitoring

*   **Logs**: Check `output/pipeline_logs/batch.log` for execution details.
*   **Sheet**: Watch the `Status` column change from `Pending` -> `Processing` -> `Completed`.
*   **Drive**: Final MP4s will appear in the specified Google Drive folder.
