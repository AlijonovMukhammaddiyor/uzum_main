# psql -h db-postgresql-blr1-80747-do-user-14120836-0.b.db.ondigitalocean.com -d defaultdb -U doadmin -p 25060


from datetime import datetime, timedelta

import pytz
from django.db import connection
from django.utils import timezone


def create_materialized_view(date_pretty_str):
    drop_materialized_view()
    drop_sku_analytics_view()
    drop_product_avg_purchase_price_view()

    create_product_analytics_monthly_materialized_view(date_pretty_str)
    create_product_analytics_weekly_materialized_view(date_pretty_str)
    create_sku_analytics_materialized_view(date_pretty_str)
    create_product_avg_purchase_price_view(date_pretty_str)
    create_product_analytics_interval_materialized_view(3, "product_analytics_3days")
    create_product_analytics_interval_materialized_view(7, "weekly_product_analytics")
    create_product_analytics_interval_materialized_view(30, "monthly_product_analytics")
    create_product_analytics_interval_materialized_view(90, "product_analytics_90days")

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            CREATE MATERIALIZED VIEW product_sku_analytics AS
            SELECT
                pa.date_pretty,
                pa.product_id,
                p.title AS product_title,
                p.created_at AS product_created_at,
                p.title_ru AS product_title_ru,
                p.category_id,
                c.title AS category_title,
                c.title_ru AS category_title_ru,
                p.characteristics AS product_characteristics,
                p.photos,
                sh.title AS shop_title,
                sh.link AS shop_link,
                pa.available_amount AS product_available_amount,
                pa.orders_amount,
                pa.reviews_amount,
                pa.orders_money,
                pa.rating,
                pa.position_in_category,
                pa.position_in_shop,
                pa.position,
                jsonb_agg(
                    json_build_object(
                        'badge_text', b.text,
                        'badge_bg_color', b.background_color,
                        'badge_text_color', b.text_color
                    )
                )::text AS badges,
                COALESCE(sa.sku_analytics, '[]') AS sku_analytics,
                COALESCE(avp.avg_purchase_price, 0) AS avg_purchase_price,
                pam.diff_orders_money AS diff_orders_money,  -- added from product_analytics_monthly
                pam.diff_orders_amount AS diff_orders_amount,  -- added from product_analytics_monthly
                pam.diff_reviews_amount AS diff_reviews_amount,  -- added from product_analytics_monthly
                paw.weekly_orders_money AS weekly_orders_money,  -- added from product_analytics_weekly
                paw.weekly_orders_amount AS weekly_orders_amount,  -- added from product_analytics_weekly
                paw.weekly_reviews_amount AS weekly_reviews_amount,  -- added from product_analytics_weekly
                wpa.total_revenue AS weekly_revenue,
                wpa.total_real_orders AS weekly_orders,
                mpa.total_revenue AS monthly_revenue,
                mpa.total_real_orders AS monthly_orders,
                pa90.total_revenue AS revenue_90_days,
                pa90.total_real_orders AS orders_90_days,
                pa3.total_revenue AS revenue_3_days,
                pa3.total_real_orders AS orders_3_days
            FROM
                product_productanalytics pa
                JOIN product_product p ON pa.product_id = p.product_id
                JOIN category_category c ON p.category_id = c."categoryId"
                JOIN shop_shop sh ON p.shop_id = sh.seller_id
                LEFT JOIN product_productanalytics_badges pb ON pa.id = pb.productanalytics_id
                LEFT JOIN badge_badge b ON pb.badge_id = b.badge_id
                LEFT JOIN sku_analytics_view sa ON pa.product_id = sa.product_id
                LEFT JOIN product_avg_purchase_price_view avp ON pa.product_id = avp.product_id
                LEFT JOIN product_analytics_monthly pam ON pa.product_id = pam.product_id -- delete this later NONEED
                LEFT JOIN product_analytics_weekly paw ON pa.product_id = paw.product_id -- delete this later NONEED
                LEFT JOIN weekly_product_analytics wpa ON pa.product_id = wpa.product_id
                LEFT JOIN monthly_product_analytics mpa ON pa.product_id = mpa.product_id
                LEFT JOIN product_analytics_90days pa90 ON pa.product_id = pa90.product_id
                LEFT JOIN product_analytics_3days pa3 ON pa.product_id = pa3.product_id
            WHERE
                pa.date_pretty = '{date_pretty_str}'
            GROUP BY
                pa.date_pretty,
                pa.product_id,
                p.title,
                p.created_at,
                p.title_ru,
                p.category_id,
                c.title,
                c.title_ru,
                p.characteristics,
                p.photos,
                sh.title,
                sh.link,
                pa.available_amount,
                pa.orders_amount,
                pa.orders_money,
                pa.reviews_amount,
                pa.rating,
                pa.position_in_category,
                pa.position_in_shop,
                pa.position,
                sa.sku_analytics,
                avp.avg_purchase_price,
                wpa.total_revenue,
                wpa.total_real_orders,
                mpa.total_revenue,
                mpa.total_real_orders,
                pa90.total_revenue,
                pa90.total_real_orders,
                pa3.total_revenue,
                pa3.total_real_orders,
                pam.diff_orders_money,  -- group by these new columns as well
                pam.diff_orders_amount,
                pam.diff_reviews_amount,
                paw.weekly_orders_money,
                paw.weekly_orders_amount,
                paw.weekly_reviews_amount;
            """
        )


def create_sku_analytics_materialized_view(date_pretty_str):
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            CREATE MATERIALIZED VIEW sku_analytics_view AS
            SELECT
                s.product_id,
                json_agg(
                    json_build_object(
                        'sku_id', sa.sku_id,
                        'available_amount', sa.available_amount,
                        'orders_amount', sa.orders_amount,
                        'purchase_price', sa.purchase_price,
                        'full_price', sa.full_price
                    )
                )::text AS sku_analytics
            FROM
                sku_skuanalytics sa
                JOIN sku_sku s ON sa.sku_id = s.sku
            WHERE
                sa.date_pretty = '{date_pretty_str}'
            GROUP BY
                s.product_id
            """
        )


def create_product_analytics_monthly_materialized_view(date_pretty):
    thirty_days_ago = (
        timezone.make_aware(datetime.now() - timedelta(days=30))
        .astimezone(pytz.timezone("Asia/Tashkent"))
        .replace(hour=0, minute=0, second=0, microsecond=0)
    )

    # If date_pretty is a datetime object, convert it to a string
    if isinstance(date_pretty, datetime):
        date_pretty = date_pretty.strftime("%Y-%m-%d")

    with connection.cursor() as cursor:
        # Drop the materialized view if it exists
        cursor.execute("DROP MATERIALIZED VIEW IF EXISTS product_analytics_monthly;")

        cursor.execute(
            """
            CREATE MATERIALIZED VIEW product_analytics_monthly AS
            WITH LatestEntries AS (
                SELECT
                    product_id,
                    MAX(created_at) as latest_date
                FROM
                    product_productanalytics
                WHERE
                    created_at <= %s
                GROUP BY
                    product_id
            )

            , CurrentEntries AS (
                SELECT
                    product_id,
                    orders_amount AS current_orders_amount,
                    orders_money AS current_orders_money,
                    reviews_amount AS current_reviews_amount
                FROM
                    product_productanalytics
                WHERE
                    date_pretty = %s
            )

            SELECT
                CE.product_id,
                LE.latest_date AS latest_date_30_days_ago,
                COALESCE(PA.orders_amount, 0) AS orders_amount_30_days_ago,
                COALESCE(PA.orders_money, 0) AS orders_money_30_days_ago,
                COALESCE(PA.reviews_amount, 0) AS reviews_amount_30_days_ago,
                CE.current_orders_amount,
                CE.current_orders_money,
                CE.current_reviews_amount,
                GREATEST(CE.current_orders_amount - COALESCE(PA.orders_amount, 0), 0) AS diff_orders_amount,
                GREATEST(CE.current_orders_money - COALESCE(PA.orders_money, 0), 0) AS diff_orders_money,
                GREATEST(CE.current_reviews_amount - COALESCE(PA.reviews_amount, 0), 0) AS diff_reviews_amount
            FROM
                CurrentEntries CE
            LEFT JOIN
                LatestEntries LE ON CE.product_id = LE.product_id
            LEFT JOIN
                product_productanalytics PA ON LE.product_id = PA.product_id AND LE.latest_date = PA.created_at;
            """,
            [thirty_days_ago, date_pretty],
        )


def create_product_analytics_interval_materialized_view(interval: int, table_name="product_analytics_interval"):
    # Convert the dates to string format if they're datetime objects

    start_date = timezone.make_aware(datetime.now() - timedelta(days=interval)).strftime("%Y-%m-%d")

    with connection.cursor() as cursor:
        drop_query = f"DROP MATERIALIZED VIEW IF EXISTS {table_name};"
        cursor.execute(drop_query)

        create_query = f"""
            CREATE MATERIALIZED VIEW {table_name} AS
            WITH StartEntries AS (
                SELECT
                    product_id,
                    SUM(real_orders_amount) as start_real_orders,
                    SUM(daily_revenue) as start_revenue
                FROM
                    product_productanalytics
                WHERE
                    date_pretty >= %s
                GROUP BY
                    product_id
            )

            SELECT
                product_id,
                SUM(start_real_orders) as total_real_orders,
                SUM(start_revenue) as total_revenue
            FROM
                StartEntries
            GROUP BY
                product_id;
            """
        cursor.execute(create_query, [start_date])


def create_product_avg_purchase_price_view(date_pretty_str):
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            CREATE MATERIALIZED VIEW product_avg_purchase_price_view AS
            SELECT
                s.product_id,
                AVG(sa.purchase_price) AS avg_purchase_price
            FROM
                sku_skuanalytics sa
                JOIN sku_sku s ON sa.sku_id = s.sku
            WHERE
                sa.date_pretty = '{date_pretty_str}'
            GROUP BY
                s.product_id
            """
        )


def drop_product_analytics_weekly_materialized_view():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            DROP MATERIALIZED VIEW IF EXISTS product_analytics_weekly
            """
        )


def drop_product_analytics_monthly_materialized_view():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            DROP MATERIALIZED VIEW IF EXISTS product_analytics_monthly
            """
        )


def drop_product_avg_purchase_price_view():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            DROP MATERIALIZED VIEW IF EXISTS product_avg_purchase_price_view
            """
        )


def drop_materialized_view():
    with connection.cursor() as cursor:
        cursor.execute(
            """
        DROP MATERIALIZED VIEW IF EXISTS product_sku_analytics;
        """
        )


def drop_sku_analytics_view():
    with connection.cursor() as cursor:
        cursor.execute(
            """
        DROP MATERIALIZED VIEW IF EXISTS sku_analytics_view;
        """
        )


def update_shop_analytics_from_materialized_view(date_pretty):
    # If date_pretty is a datetime object, convert it to a string
    if isinstance(date_pretty, datetime):
        date_pretty = date_pretty.strftime("%Y-%m-%d")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE shop_shopanalytics sa
            SET
                monthly_total_orders = mv.monthly_total_orders,
                monthly_total_revenue = mv.monthly_total_revenue
            FROM shop_analytics_monthly mv
            WHERE
                sa.shop_id = mv.shop_id
                AND sa.date_pretty = %s
            """,
            [date_pretty],
        )

def create_combined_shop_analytics_materialized_view(date_pretty):
    # Create interval materialized views for monthly and 3 months

    with connection.cursor() as cursor:
        cursor.execute(
            """
            DROP MATERIALIZED VIEW IF EXISTS combined_shop_analytics;
            """
        )

    create_shop_analytics_interval_materialized_view(date_pretty, 30)
    create_shop_analytics_interval_materialized_view(date_pretty, 90)
    create_shop_analytics_monthly_materialized_view(date_pretty)

    with connection.cursor() as cursor:
        # Create the consolidated materialized view
        cursor.execute(
            """
            CREATE MATERIALIZED VIEW combined_shop_analytics AS
            SELECT
                s.seller_id,
                s.title,
                s.link,
                s.registration_date,
                s.avatar,
                sa.total_products,
                sa.total_orders,
                sa.total_reviews,
                sa.average_purchase_price,
                sa.rating,
                monthly.total_orders_30days AS monthly_orders,
                monthly.total_revenue_30days AS monthly_revenue,
                quarterly.total_orders_90days AS quarterly_orders,
                quarterly.total_revenue_90days AS quarterly_revenue,
                mon.monthly_total_orders as monthly_transactions
            FROM
                shop_shop s
            JOIN
                shop_shopanalytics sa ON s.seller_id = sa.shop_id AND sa.date_pretty = %s
            LEFT JOIN
                shop_analytics_30days monthly ON s.seller_id = monthly.shop_id
            LEFT JOIN
                shop_analytics_90days quarterly ON s.seller_id = quarterly.shop_id
            LEFT JOIN
                shop_analytics_monthly mon ON s.seller_id = mon.shop_id;
            """,
            [date_pretty],
        )


def create_shop_analytics_interval_materialized_view(date_pretty, interval_days):
    end_date = (
        timezone.make_aware(datetime.strptime(date_pretty, "%Y-%m-%d"))
        .astimezone(pytz.timezone("Asia/Tashkent"))
        .replace(hour=23, minute=59, second=0, microsecond=0)
    )
    interval_days -= 1
    start_date = end_date - timedelta(days=interval_days)

    # If date_pretty is a datetime object, convert it to a string
    if isinstance(date_pretty, datetime):
        date_pretty = date_pretty.strftime("%Y-%m-%d")

    with connection.cursor() as cursor:
        # Create a name for the materialized view based on the interval
        view_name = f"shop_analytics_{interval_days}days"

        # Drop the materialized view if it exists
        cursor.execute(f"DROP MATERIALIZED VIEW IF EXISTS {view_name};")

        cursor.execute(
            f"""
            CREATE MATERIALIZED VIEW {view_name} AS
            SELECT
                shop_id,
                SUM(daily_orders) AS total_orders_{interval_days}days,
                SUM(daily_revenue) AS total_revenue_{interval_days}days
            FROM
                shop_shopanalytics
            WHERE
                date_pretty::DATE BETWEEN %s AND %s
            GROUP BY
                shop_id;
            """,
            [start_date, end_date],
        )

def create_shop_analytics_monthly_materialized_view(date_pretty):
    thirty_days_ago = (
        timezone.make_aware(datetime.now() - timedelta(days=30))
        .astimezone(pytz.timezone("Asia/Tashkent"))
        .replace(hour=0, minute=0, second=0, microsecond=0)
    )

    # If date_pretty is a datetime object, convert it to a string
    if isinstance(date_pretty, datetime):
        date_pretty = date_pretty.strftime("%Y-%m-%d")

    with connection.cursor() as cursor:
        # Drop the materialized view if it exists
        cursor.execute("DROP MATERIALIZED VIEW IF EXISTS shop_analytics_monthly;")

        cursor.execute(
            """
            CREATE MATERIALIZED VIEW shop_analytics_monthly AS
            WITH LatestEntries AS (
                SELECT
                    shop_id,
                    MAX(created_at) as latest_date
                FROM
                    shop_shopanalytics
                WHERE
                    created_at <= %s
                GROUP BY
                    shop_id
            )

            , CurrentEntries AS (
                SELECT
                    shop_id,
                    total_orders AS current_total_orders
                FROM
                    shop_shopanalytics
                WHERE
                    date_pretty = %s
            )

            SELECT
                CE.shop_id,
                LE.latest_date AS latest_date_30_days_ago,
                COALESCE(PA.total_orders, 0) AS orders_amount_30_days_ago,
                COALESCE(PA.total_revenue, 0) AS orders_money_30_days_ago,
                CE.current_total_orders,
                GREATEST(CE.current_total_orders - COALESCE(PA.total_orders, 0), 0) AS monthly_total_orders
            FROM
                CurrentEntries CE
            LEFT JOIN
                LatestEntries LE ON CE.shop_id = LE.shop_id
            LEFT JOIN
                shop_shopanalytics PA ON LE.shop_id = PA.shop_id AND LE.latest_date = PA.created_at;
            """,
            [thirty_days_ago, date_pretty],
        )


def create_product_analytics_weekly_materialized_view(date_pretty):
    thirty_days_ago = (
        timezone.make_aware(datetime.now() - timedelta(days=7))
        .astimezone(pytz.timezone("Asia/Tashkent"))
        .replace(hour=0, minute=0, second=0, microsecond=0)
    )

    # If date_pretty is a datetime object, convert it to a string
    if isinstance(date_pretty, datetime):
        date_pretty = date_pretty.strftime("%Y-%m-%d")

    with connection.cursor() as cursor:
        # Drop the materialized view if it exists
        cursor.execute("DROP MATERIALIZED VIEW IF EXISTS product_analytics_weekly;")

        cursor.execute(
            """
            CREATE MATERIALIZED VIEW product_analytics_weekly AS
            WITH LatestEntries AS (
                SELECT
                    product_id,
                    MAX(created_at) as latest_date
                FROM
                    product_productanalytics
                WHERE
                    created_at <= %s
                GROUP BY
                    product_id
            )

            , CurrentEntries AS (
                SELECT
                    product_id,
                    orders_amount AS current_orders_amount,
                    orders_money AS current_orders_money,
                    reviews_amount AS current_reviews_amount
                FROM
                    product_productanalytics
                WHERE
                    date_pretty = %s
            )

            SELECT
                CE.product_id,
                LE.latest_date AS latest_date_7_days_ago,
                COALESCE(PA.orders_amount, 0) AS orders_amount_7_days_ago,
                COALESCE(PA.orders_money, 0) AS orders_money_7_days_ago,
                COALESCE(PA.reviews_amount, 0) AS reviews_amount_7_days_ago,
                CE.current_orders_amount,
                CE.current_orders_money,
                CE.current_reviews_amount,
                GREATEST(CE.current_orders_amount - COALESCE(PA.orders_amount, 0), 0) AS weekly_orders_amount,
                GREATEST(CE.current_orders_money - COALESCE(PA.orders_money, 0), 0) AS weekly_orders_money,
                GREATEST(CE.current_reviews_amount - COALESCE(PA.reviews_amount, 0), 0) AS weekly_reviews_amount
            FROM
                CurrentEntries CE
            LEFT JOIN
                LatestEntries LE ON CE.product_id = LE.product_id
            LEFT JOIN
                product_productanalytics PA ON LE.product_id = PA.product_id AND LE.latest_date = PA.created_at;
            """,
            [thirty_days_ago, date_pretty],
        )
