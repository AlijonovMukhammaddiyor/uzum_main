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
    available_amount = models.IntegerField(default=0)
    orders_amount = models.IntegerField(default=0)
    purchase_price = models.FloatField(default=0, db_index=True)
    full_price = models.FloatField(default=None, null=True, blank=True)
    date_pretty = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        default=get_today_pretty,
    )

    def __str__(self) -> str:
        return f"{self.sku} - {self.sku.product.title}"


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


def set_orders_amount_sku(date_pretty: str):
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE sku_skuanalytics sa
                SET orders_amount = sub.sku_real_orders_amount
                FROM (
                    SELECT
                        sa.id AS analytics_id,
                        -- Determine the real_orders_amount for each SKU
                        CASE
                            -- If real_orders_amount is 0, set all SKU's orders_amount to 0
                            WHEN pd.real_orders_amount = 0 THEN 0
                            -- If SKU's difference in available_amount is 0, set its orders_amount to 0
                            WHEN sd.diff_available_amount = 0 THEN 0
                            -- When the total SKU available amount difference equals product's real orders amount, use the SKU's available amount difference
                            WHEN ss.total_diff_available = pd.real_orders_amount THEN sd.diff_available_amount
                            -- Otherwise, calculate the proportional orders amount for each SKU
                            ELSE
                                (sd.diff_available_amount / NULLIF(ss.total_diff_available, 0)) * pd.real_orders_amount
                                + CASE
                                    -- Adjust the orders_amount for SKUs based on the remainder when dividing their proportional orders by the total available amount difference
                                    WHEN ROW_NUMBER() OVER (PARTITION BY sku.product_id ORDER BY remainder DESC, sku.sku) <= pd.real_orders_amount - SUM(proportional_orders) OVER (PARTITION BY sku.product_id)
                                    THEN 1
                                    ELSE 0
                                END
                        END AS sku_real_orders_amount
                    FROM
                        -- Join SKU table with SKU analytics for the given date
                        sku_sku sku
                    JOIN
                        sku_skuanalytics sa ON sa.sku_id = sku.sku AND sa.date_pretty = '{date_pretty}'
                    -- Get the previous day's SKU analytics using the materialized view
                    LEFT JOIN
                        sku_latest_analytics prev_sa ON prev_sa.sku_id = sa.sku_id
                    -- Join with product analytics for the given date
                    LEFT JOIN
                        product_productanalytics pa ON pa.product_id = sku.product_id AND pa.date_pretty = '{date_pretty}'
                    -- Get the previous day's product analytics using the materialized view
                    LEFT JOIN
                        product_latest_analytics prev_pa ON prev_pa.product_id = pa.product_id
                    -- Calculate the difference in available_amount and orders_amount for products between today and the previous day
                    CROSS JOIN LATERAL (
                        SELECT
                            COALESCE(prev_sa.latest_available_amount, 0) - COALESCE(sa.available_amount, 0) AS diff_available_amount, -- Corrected subtraction
                            COALESCE(pa.orders_amount, 0) - COALESCE(prev_pa.latest_orders_amount, 0) AS diff_orders_amount,  -- Original subtraction
                            -- Determine the real orders amount for the product
                            GREATEST(
                                COALESCE(pa.orders_amount, 0) - COALESCE(prev_pa.latest_orders_amount, 0),  -- Original subtraction
                                COALESCE(prev_pa.latest_available_amount, 0) - COALESCE(pa.available_amount, 0)  -- Corrected subtraction
                            ) AS real_orders_amount
                    ) AS pd
                    -- Calculate the difference in available_amount for SKUs between today and the previous day
                    CROSS JOIN LATERAL (
                        SELECT
                            COALESCE(prev_sa.latest_available_amount, 0) - COALESCE(sa.available_amount, 0) AS diff_available_amount, -- Corrected subtraction
                            -- Calculate the proportional orders amount for each SKU
                            (COALESCE(prev_sa.latest_available_amount, 0) - COALESCE(sa.available_amount, 0)) * pd.real_orders_amount AS proportional_orders, -- Corrected subtraction
                            -- Calculate the remainder when dividing the SKU's proportional orders by the total available amount difference
                            (COALESCE(prev_sa.latest_available_amount, 0) - COALESCE(sa.available_amount, 0)) * pd.real_orders_amount % NULLIF(SUM(COALESCE(prev_sa.latest_available_amount, 0) - COALESCE(sa.available_amount, 0)) OVER (PARTITION BY sku.product_id), 0) AS remainder -- Corrected subtraction
                    ) AS sd
                    -- Calculate the total difference in available_amount for all SKUs under the same product
                    CROSS JOIN LATERAL (
                        SELECT
                            SUM(COALESCE(prev_sa.latest_available_amount, 0) - COALESCE(sa.available_amount, 0)) OVER (PARTITION BY sku.product_id) AS total_diff_available -- Corrected subtraction
                    ) AS ss
                ) AS sub
                WHERE sa.id = sub.analytics_id;
                """
            )
    except Exception as e:
        print(e)
        traceback.print_exc()
        return False
