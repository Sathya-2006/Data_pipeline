
import pandas as pd
from sqlalchemy import create_engine, text

# 1. DATABASE CONNECTION
engine = create_engine(
    "postgresql+psycopg://sathyaruba@localhost:5432/sales_warehouse"
)


def run_pipeline():

    # STEP 1: EXTRACT
    print("\nSTEP 1: EXTRACT")

    df = pd.read_csv("sales.csv")

    print(f"Records extracted: {len(df)}")
    print(df)

    # STEP 2: TRANSFORM
    print("\nSTEP 2: TRANSFORM")

    # Check required columns
    required_columns = [
        "order_id",
        "product",
        "quantity",
        "unit_price"
    ]

    missing_columns = set(required_columns) - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {missing_columns}"
        )

    # Convert numeric columns safely
    df["quantity"] = pd.to_numeric(
        df["quantity"], errors="coerce"
    )

    df["unit_price"] = pd.to_numeric(
        df["unit_price"], errors="coerce"
    )

    # Generate rejection reasons
    reasons = pd.Series("", index=df.index, dtype="object")

    # Validate order ID
    bad_order_id = (
        df["order_id"].isna()
        | df["order_id"].astype(str).str.strip().eq("")
    )

    reasons.loc[bad_order_id] += (
        "Missing or empty order_id; "
    )

    # Validate product
    bad_product = (
        df["product"].isna()
        | df["product"].astype(str).str.strip().eq("")
    )

    reasons.loc[bad_product] += (
        "Missing or empty product; "
    )

    # Validate quantity
    bad_quantity = (
        df["quantity"].isna()
        | (df["quantity"] <= 0)
    )

    reasons.loc[bad_quantity] += (
        "Quantity must be greater than 0; "
    )

    # Validate unit price
    bad_price = (
        df["unit_price"].isna()
        | (df["unit_price"] < 0)
    )

    reasons.loc[bad_price] += (
        "Unit price must be >= 0; "
    )

    # Separate valid and invalid records
    valid_mask = reasons.eq("")

    valid_df = df.loc[valid_mask].copy()
    invalid_df = df.loc[~valid_mask].copy()

    # Add rejection reasons
    invalid_df["rejection_reason"] = (
        reasons.loc[~valid_mask].str.rstrip("; ")
    )

    # Calculate revenue for valid records
    valid_df["revenue"] = (
        valid_df["quantity"] * valid_df["unit_price"]
    )

    print(f"Valid records: {len(valid_df)}")
    print(f"Invalid records: {len(invalid_df)}")

    print("\nRejected records with reasons:")
    print(invalid_df)

    # STEP 3: LOAD
    print("\nSTEP 3: LOAD")

    with engine.begin() as connection:

        # Create fact table
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS sales_fact (
                order_id TEXT PRIMARY KEY,
                product TEXT NOT NULL,
                quantity INTEGER NOT NULL
                    CHECK (quantity > 0),
                unit_price NUMERIC(12, 2) NOT NULL
                    CHECK (unit_price >= 0),
                revenue NUMERIC(14, 2) NOT NULL
            )
        """))

        # Create quarantine table
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS sales_quarantine (
                quarantine_id BIGINT
                    GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                order_id TEXT,
                product TEXT,
                quantity NUMERIC,
                unit_price NUMERIC,
                rejection_reason TEXT NOT NULL
            )
        """))

        print("Database tables are ready!")

        # STEP 3A: REFRESH QUARANTINE TABLE
        connection.execute(
            text("DELETE FROM sales_quarantine")
        )

        if not invalid_df.empty:

            quarantine_columns = [
                "order_id",
                "product",
                "quantity",
                "unit_price",
                "rejection_reason"
            ]

            invalid_df[quarantine_columns].to_sql(
                name="sales_quarantine",
                con=connection,
                if_exists="append",
                index=False
            )

        print("Quarantine table refreshed successfully!")

        # STEP 3B: CREATE STAGING TABLE
        if not valid_df.empty:

            valid_df.to_sql(
                name="sales_staging",
                con=connection,
                if_exists="replace",
                index=False
            )

            # STEP 3C: INCREMENTAL LOAD + UPSERT
            connection.execute(text("""
                INSERT INTO sales_fact (
                    order_id,
                    product,
                    quantity,
                    unit_price,
                    revenue
                )
                SELECT
                    order_id,
                    product,
                    quantity,
                    unit_price,
                    revenue
                FROM sales_staging
                ON CONFLICT (order_id)
                DO UPDATE SET
                    product = EXCLUDED.product,
                    quantity = EXCLUDED.quantity,
                    unit_price = EXCLUDED.unit_price,
                    revenue = EXCLUDED.revenue
            """))

            # Remove staging table
            connection.execute(
                text("DROP TABLE sales_staging")
            )

        print("Incremental load and upsert completed!")

    print("Valid records loaded into PostgreSQL!")

    # STEP 4: VERIFY
    print("\nSTEP 4: VERIFY")

    with engine.connect() as connection:

        # Verify fact table
        result = connection.execute(text("""
            SELECT
                COUNT(*) AS total_records,
                COALESCE(SUM(revenue), 0) AS total_revenue
            FROM sales_fact
        """))

        row = result.fetchone()

        print(f"Orders in database: {row[0]}")
        print(f"Total revenue: {row[1]}")

        # Verify quarantine table
        quarantine_result = connection.execute(text("""
            SELECT COUNT(*)
            FROM sales_quarantine
        """))

        quarantine_count = quarantine_result.scalar()

        print(
            f"Records in quarantine table: {quarantine_count}"
        )

        # Display loaded orders
        orders_result = connection.execute(text("""
            SELECT
                order_id,
                product,
                quantity,
                unit_price,
                revenue
            FROM sales_fact
            ORDER BY order_id
        """))

        print("\nOrders in sales_fact:")
        for order in orders_result.fetchall():
            print(order)

    print("\nETL PIPELINE COMPLETED SUCCESSFULLY!")



def run_data_quality_tests():

    print("\nSTEP 5: AUTOMATED DATA QUALITY TESTS")

    with engine.connect() as connection:

        # TEST 1: No invalid quantities in sales_fact
        bad_quantity = connection.execute(text("""
            SELECT COUNT(*)
            FROM sales_fact
            WHERE quantity <= 0
        """)).scalar()

        # TEST 2: No duplicate order IDs
        duplicate_orders = connection.execute(text("""
            SELECT COUNT(*)
            FROM (
                SELECT order_id
                FROM sales_fact
                GROUP BY order_id
                HAVING COUNT(*) > 1
            ) AS duplicates
        """)).scalar()

        # TEST 3: No negative unit prices
        bad_prices = connection.execute(text("""
            SELECT COUNT(*)
            FROM sales_fact
            WHERE unit_price < 0
        """)).scalar()

        # TEST 4: Revenue must equal quantity * unit_price
        revenue_errors = connection.execute(text("""
            SELECT COUNT(*)
            FROM sales_fact
            WHERE revenue <> quantity * unit_price
        """)).scalar()

        # TEST 5: Current sample's invalid order must be quarantined
        quarantine_check = connection.execute(text("""
            SELECT COUNT(*)
            FROM sales_quarantine
            WHERE order_id = 'O103'
              AND rejection_reason LIKE
                  '%Quantity must be greater than 0%'
        """)).scalar()

    # Store test results
    tests = [
        (
            "Positive quantity",
            bad_quantity == 0
        ),
        (
            "Unique order IDs",
            duplicate_orders == 0
        ),
        (
            "Non-negative unit prices",
            bad_prices == 0
        ),
        (
            "Revenue calculation",
            revenue_errors == 0
        ),
        (
            "Invalid O103 quarantined correctly",
            quarantine_check == 1
        )
    ]

    # Print results
    for test_name, passed in tests:
        status = "PASS" if passed else "FAIL"
        print(f"{status}: {test_name}")

    # Fail the test step if any check fails
    failed_tests = [
        name for name, passed in tests if not passed
    ]

    if failed_tests:
        raise AssertionError(
            f"Data quality tests failed: {failed_tests}"
        )

    print("\nALL DATA QUALITY TESTS PASSED!")


if __name__ == "__main__":
    run_pipeline()
    run_data_quality_tests()

