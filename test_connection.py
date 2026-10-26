from sqlalchemy import create_engine, text

engine = create_engine("postgresql+psycopg://sathyaruba@localhost:5432/sales_warehouse")

with engine.connect() as connection:
    result = connection.execute(text("SELECT current_database(), version()"))

    print(result.fetchone())

print("Postgresql connection successfully !")