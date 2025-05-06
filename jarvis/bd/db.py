
import pg8000
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

DBNAME = 't_82ql'
DBUSERNAME =  't'
DBPASSWORD =  'LJth9webo4UzXUXN5TX79dS0AULEh7vF'
DBHOST = 'dpg-d0ct2p8dl3ps73ehq910-a.oregon-postgres.render.com'
DBPORT =  '5432'

def get_db_connection():

    return pg8000.connect(
        user=DBUSERNAME,
        password=DBPASSWORD,
        host=DBHOST,
        port=DBPORT,
        database=DBNAME
    )


def establish_db_connection():
    try:

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                sql_file_path = 'createTables.sql'
                with open(sql_file_path, 'r') as file:
                    sql_queries = file.read()

                cursor.execute(sql_queries)
                conn.commit()

                logger.info("Database tables ensured to exist.")

    except Exception as e:
        logger.error(f"Database Error: {str(e)}", exc_info=True)
        raise




establish_db_connection()

