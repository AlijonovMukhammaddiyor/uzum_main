from datetime import datetime
import traceback
import uuid

from django.db import connection, models
import pytz

from uzum.badge.models import Badge
from uzum.utils.general import get_today_pretty


class Sku(models.Model):
    """
    Sku - is the product variation.
    I just made separate model for it, because it has different and detailed information.
    """

    sku = models.IntegerField(unique=True, primary_key=True)
    product = models.ForeignKey("product.Product", on_delete=models.DO_NOTHING, related_name="skus", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    barcode = models.CharField(max_length=255, null=True, blank=True)
    charity_profit = models.FloatField(default=0)
    discount_badge = models.ForeignKey(Badge, on_delete=models.DO_NOTHING, related_name="skus", null=True)
    payment_per_month = models.FloatField(default=0)
    vat_amount = models.FloatField(default=0)
    vat_price = models.FloatField(default=0)
    vat_rate = models.FloatField(default=0)
    video_url = models.TextField(null=True, blank=True)
    characteristics = models.TextField(null=True, blank=True)  # json.dumps(characteristics)


class SkuAnalytics(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sku = models.ForeignKey(Sku, on_delete=models.DO_NOTHING, related_name="analytics")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    available_amount = models.IntegerField(default=0, db_index=True)
    orders_amount = models.IntegerField(default=0, null=False)
    orders_money = models.FloatField(default=0, null=False)
    purchase_price = models.FloatField(default=0, db_index=True)
    full_price = models.FloatField(default=None, null=True, blank=True)
    date_pretty = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        default=get_today_pretty,
    )
    delta_available_amount = models.IntegerField(default=0, blank=True, null=True)

    def __str__(self) -> str:
        return f"{self.sku} - {self.sku.product.title}"

    @staticmethod
    def update_delta_available_amount(date_pretty: str):
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE sku_skuanalytics sa
                    SET delta_available_amount = (COALESCE(lsa.latest_available_amount, 0) - sa.available_amount)
                    FROM sku_latest_analytics lsa
                    WHERE sa.sku_id = lsa.sku_id
                    AND sa.date_pretty = %s
                    """,
                    [date_pretty],
                )
        except Exception as e:
            print(e)

    @staticmethod
    def update_orders_money(date_pretty: str):
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE sku_skuanalytics sa
                    SET orders_money = sa.orders_amount * sa.purchase_price
                    WHERE sa.date_pretty = %s
                    """,
                    [date_pretty],
                )
        except Exception as e:
            print(e)


class LatestSkuAnalyticsView(models.Model):
    sku_id = models.IntegerField(primary_key=True)
    last_updated_at = models.DateTimeField()
    latest_purchase_price = models.DecimalField(max_digits=10, decimal_places=2)
    latest_orders_amount = models.IntegerField()  # If you have this value for SKUs
    latest_available_amount = models.IntegerField()

    class Meta:
        managed = False
        db_table = "sku_latest_analytics"


def create_sku_latestanalytics(date_pretty: str):
    # Convert date_pretty to a timezone-aware datetime object
    date = (
        pytz.timezone("Asia/Tashkent")
        .localize(datetime.strptime(date_pretty, "%Y-%m-%d"))
        .replace(hour=23, minute=59, second=59, microsecond=999999)
    )

    with connection.cursor() as cursor:
        # Drop the materialized view if it exists
        cursor.execute("DROP MATERIALIZED VIEW IF EXISTS sku_latest_analytics")

        # Create the materialized view
        cursor.execute(
            f"""
            CREATE MATERIALIZED VIEW sku_latest_analytics AS
            SELECT DISTINCT ON (sku_id) sku_id, created_at as last_updated_at,
                purchase_price as latest_purchase_price,
                available_amount as latest_available_amount
                -- Add orders_amount if you have it for SKUs
            FROM sku_skuanalytics
            WHERE created_at <= '{date}'
            ORDER BY sku_id, created_at DESC
        """
        )


# def set_orders_amount_sku(date_pretty: str):
#     try:
#         with connection.cursor() as cursor:
#             cursor.execute(
#                 f"""
#                 UPDATE sku_skuanalytics sa
#                 SET orders_amount = sub.sku_real_orders_amount
#                 FROM (
#                     SELECT
#                         sa.id AS analytics_id,
#                         -- Determine the real_orders_amount for each SKU
#                         CASE
#                             -- If real_orders_amount is 0, set all SKU's orders_amount to 0
#                             -- WHEN pd.real_orders_amount = 0 THEN 0
#                             -- If SKU's difference in available_amount is 0, set its orders_amount to 0
#                             WHEN sd.diff_available_amount = 0 THEN 0
#                             -- When the total SKU available amount difference equals product's real orders amount, use the SKU's available amount difference
#                             WHEN ss.total_diff_available = pd.real_orders_amount THEN sd.diff_available_amount
#                             -- Otherwise, calculate the proportional orders amount for each SKU
#                             ELSE
#                                 (sd.diff_available_amount / NULLIF(ss.total_diff_available, 0)) * pd.real_orders_amount
#                                 + CASE
#                                     -- Adjust the orders_amount for SKUs based on the remainder when dividing their proportional orders by the total available amount difference
#                                     WHEN ROW_NUMBER() OVER (PARTITION BY sku.product_id ORDER BY remainder DESC, sku.sku) <= pd.real_orders_amount - SUM(proportional_orders) OVER (PARTITION BY sku.product_id)
#                                     THEN 1
#                                     ELSE 0
#                                 END
#                         END AS sku_real_orders_amount
#                     FROM
#                         -- Join SKU table with SKU analytics for the given date
#                         sku_sku sku
#                     JOIN
#                         sku_skuanalytics sa ON sa.sku_id = sku.sku AND sa.date_pretty = '{date_pretty}'
#                     -- Get the previous day's SKU analytics using the materialized view
#                     LEFT JOIN
#                         sku_latest_analytics prev_sa ON prev_sa.sku_id = sa.sku_id
#                     -- Join with product analytics for the given date
#                     LEFT JOIN
#                         product_productanalytics pa ON pa.product_id = sku.product_id AND pa.date_pretty = '{date_pretty}'
#                     -- Get the previous day's product analytics using the materialized view
#                     LEFT JOIN
#                         product_latest_analytics prev_pa ON prev_pa.product_id = pa.product_id
#                     -- Calculate the difference in available_amount and orders_amount for products between today and the previous day
#                     CROSS JOIN LATERAL (
#                         SELECT
#                             -- Determine the real orders amount for the product
#                             GREATEST(
#                                 COALESCE(pa.orders_amount, 0) - COALESCE(prev_pa.latest_orders_amount, 0),  -- Original subtraction
#                                 COALESCE(prev_pa.latest_available_amount, 0) - COALESCE(pa.available_amount, 0)  -- Corrected subtraction
#                             ) AS real_orders_amount
#                     ) AS pd
#                     -- Calculate the total difference in available_amount for all SKUs under the same product
#                     CROSS JOIN LATERAL (
#                         SELECT
#                             SUM(GREATEST(0, COALESCE(prev_sa.latest_available_amount, 0) - COALESCE(sa.available_amount, 0))) OVER (PARTITION BY sku.product_id) AS total_diff_available -- Corrected subtraction
#                     ) AS ss
#                     -- Calculate the difference in available_amount for SKUs between today and the previous day
#                     CROSS JOIN LATERAL (
#                         SELECT
#                             GREATEST(0, COALESCE(prev_sa.latest_available_amount, 0) - COALESCE(sa.available_amount, 0)) AS diff_available_amount,
#                             -- Calculate the proportional orders amount for each SKU
#                             GREATEST(0, COALESCE(prev_sa.latest_available_amount, 0) - COALESCE(sa.available_amount, 0)) / NULLIF(ss.total_diff_available, 0) * pd.real_orders_amount AS proportional_orders,
#                             -- Calculate the remainder when dividing the SKU's proportional orders by the total available amount difference (this might be reconsidered or removed based on the exact requirements)
#                             GREATEST(0, COALESCE(prev_sa.latest_available_amount, 0) - COALESCE(sa.available_amount, 0)) / NULLIF(ss.total_diff_available, 0) * pd.real_orders_amount % NULLIF(SUM(GREATEST(0, COALESCE(prev_sa.latest_available_amount, 0) - COALESCE(sa.available_amount, 0))) OVER (PARTITION BY sku.product_id), 0) AS remainder
#                         ) AS sd
#                 ) AS sub
#                 WHERE sa.id = sub.analytics_id;
#                 """
#             )
#     except Exception as e:
#         print(e)
#         traceback.print_exc()
#         return False


def set_orders_amount_sku(date_pretty: str):
    try:
        with connection.cursor() as cursor:
            # Create a temporary table for calculations
            cursor.execute(
                f"""
                DROP TABLE IF EXISTS tmp_orders_distribution;

                CREATE TEMP TABLE tmp_orders_distribution AS
                SELECT
                    sku.product_id,
                    sa.sku_id,
                    sa.delta_available_amount,
                    pa.real_orders_amount
                FROM
                    sku_sku sku
                JOIN
                    sku_skuanalytics sa ON sa.sku_id = sku.sku AND sa.date_pretty = '{date_pretty}'
                JOIN
                    product_productanalytics pa ON pa.product_id = sku.product_id AND pa.date_pretty = '{date_pretty}';
            """
            )

            # Compute necessary values and Update the orders_amount
            cursor.execute(
                f"""
                WITH ProductTotals AS (
                    SELECT
                        product_id,
                        SUM(delta_available_amount) AS total_sku_delta,
                        AVG(real_orders_amount) -
                        SUM(CASE WHEN delta_available_amount BETWEEN 0 AND real_orders_amount THEN delta_available_amount ELSE 0 END) AS remaining_amount,
                        COUNT(*) FILTER (WHERE delta_available_amount <= 0) AS skus_with_no_delta,
                        AVG(real_orders_amount) AS real_orders_amount,
                        MAX(delta_available_amount) AS max_delta
                    FROM
                        tmp_orders_distribution
                    GROUP BY product_id
                )

                UPDATE sku_skuanalytics sa
                SET
                    orders_amount = CASE
                        -- Rule 1: If total_sku_delta matches real_orders_amount
                        WHEN t.total_sku_delta = t.real_orders_amount THEN tmp.delta_available_amount

                        -- if real_orders_amount is negative or 0, set all SKU's orders_amount to 0
                        WHEN t.real_orders_amount <= 0 THEN 0

                        -- Rule 2: If delta_available_amount is between 0 and real_orders_amount
                        WHEN tmp.delta_available_amount BETWEEN 1 AND t.real_orders_amount THEN tmp.delta_available_amount

                        -- Rule 3: If delta_available_amount exceeds real_orders_amount, is the max_delta for the product, and is the first when ordered by sku_id
                        WHEN tmp.delta_available_amount > t.real_orders_amount AND tmp.delta_available_amount = t.max_delta AND tmp.sku_id = (
                            SELECT sku_id FROM tmp_orders_distribution
                            WHERE product_id = tmp.product_id AND delta_available_amount = t.max_delta
                            ORDER BY sku_id
                            LIMIT 1
                        ) THEN t.remaining_amount

                        -- Rule 4: If the delta_available_amount is not the one that took all the remaining_amount, but it's more than real_orders_amount
                        WHEN tmp.delta_available_amount > t.real_orders_amount THEN 0

                        -- Rule 5: If any SKU of the product had a delta_available_amount greater than or equal to real_orders_amount, then set to 0
                        WHEN EXISTS (
                            SELECT 1 FROM tmp_orders_distribution
                            WHERE product_id = tmp.product_id AND delta_available_amount >= real_orders_amount
                        ) THEN 0

                        -- Rule 6: Distribute remaining amount equally for skus with delta_available_amount = 0
                        ELSE COALESCE(t.remaining_amount / NULLIF(t.skus_with_no_delta, 0), 0)
                    END
                FROM
                    tmp_orders_distribution tmp
                JOIN
                    ProductTotals t ON t.product_id = tmp.product_id
                WHERE
                    sa.sku_id = tmp.sku_id AND sa.date_pretty = '{date_pretty}';
            """
            )

    except Exception as e:
        print(e)
        traceback.print_exc()
        return False
