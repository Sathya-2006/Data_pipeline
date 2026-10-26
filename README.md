# Data Pipeline Project

## Overview
A Python-based ETL pipeline that extracts data from a CSV file, transforms it using Pandas, validates data quality, and loads the cleaned data into PostgreSQL.

## Tech Stack
- Python
- Pandas
- PostgreSQL
- SQLAlchemy
- Git and GitHub

## Pipeline Workflow
1. Extract data from the source CSV.
2. Validate and clean the data using Pandas.
3. Run data quality checks.
4. Load validated records into PostgreSQL.
5. Test database connectivity and pipeline results.

## Project Structure
- `etl_pipeline.py` — ETL pipeline implementation
- `test_connection.py` — Database connection test
- `sales.csv` — Sample input data
- `README.md` — Project documentation

## How to Run
1. Create and activate a Python virtual environment.
2. Install the required dependencies.
3. Configure your PostgreSQL connection securely using environment variables.
4. Run `python etl_pipeline.py`.

## Data Quality
The pipeline is designed to validate input data before loading it into the database.