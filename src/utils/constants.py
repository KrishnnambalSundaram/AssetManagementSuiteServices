PREDEFINED_SCRIPTS = [
        {
            "name": "User Disabling",
            "description": "Disable users who have not logged in for a specified number of days",
            "script": "user_disabling",
            "parameters": [
                {
                    "name": "days_threshold",
                    "type": "number",
                    "description": "The number of days since the last login to consider a user inactive",
                },
                {
                    "name": "dry_run",
                    "type": "boolean",
                    "description": "Whether to run the script in dry run mode",
                },
            ],
        },
        {
            "name": "Job Duration Notification",
            "description": "Send a notification if a job takes longer than a specified duration",
            "script": "delayed_jobs",
            "parameters": [
                {
                    "name": "duration_threshold",
                    "type": "number",
                    "description": "The duration threshold in minutes to consider a job delayed",
                },
            ],
        },
        {
            "name": "Unused Connections Report",
            "description": "Identify and report connections that are not being used by any mappings or other objects",
            "script": "unused_connections",
            "parameters": [],
        },
        {
            "name": "Incremental Log Sync",
            "description": "Sync logs from Informatica to the database",
            "script": "incremental_log_sync",
            "parameters": [],
        },
        {
            "name": "IPU Utilization Summarizer",
            "description": "Analyze metering data and identify meters with significant usage changes",
            "script": "metric_summarizer",
            "parameters": [
                {
                    "name": "frequency",
                    "type": "string",
                    "description": "Frequency of analysis: 'daily', 'weekly', or 'monthly'",
                    "enum": ["daily", "weekly", "monthly"],
                },
                {
                    "name": "change_threshold",
                    "type": "number",
                    "description": "Percentage threshold for change detection (e.g., 10 for 10%)",
                },
            ],
        },
    ]