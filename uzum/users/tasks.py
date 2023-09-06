import datetime
import time
import traceback
import pandas as pd
import pytz
from django.utils import timezone
from django.db.models import OuterRef, Subquery
import requests
from uzum.product.models import ProductAnalytics, ProductAnalyticsView
from uzum.shop.models import ShopAnalytics
from uzum.users.models import User
from uzum.utils.general import get_today_pretty, get_today_pretty_fake
import io
from openpyxl.styles import PatternFill, Border, Side, Font
from openpyxl.utils.dataframe import dataframe_to_rows


def prepare_shop_statistics(user, shop):
    try:
        print("Shop Daily Sales Report for shop: ", shop.title, " and user: ", user.username)
        start = time.time()

        today_pretty = get_today_pretty()
        date = today_pretty

        start_date = timezone.make_aware(
            datetime.datetime.strptime(date, "%Y-%m-%d"), timezone=pytz.timezone("Asia/Tashkent")
        ).replace(hour=0, minute=0, second=0, microsecond=0)

        def calculate_diff(target, before):
            """
            Helper function to calculate the difference between the target and before value.
            """
            if target is not None and before is not None:
                return target - before
            return target

        # analytics for today
        analytics_date = (
            ProductAnalyticsView.objects.filter(shop_link=shop.link)
            .values(
                "product_id",
                "product_title",
                "product_title_ru",
                "category_title",
                "category_title_ru",
                "orders_amount",
                "product_available_amount",
                "reviews_amount",
                "rating",
                "position_in_category",
                "avg_purchase_price",
                "orders_money",
                "diff_orders_amount",
                "diff_reviews_amount",
                "diff_orders_money",
                "weekly_orders_money",
                "weekly_orders_amount",
                "weekly_reviews_amount",
            )
            .order_by("-orders_amount")
        )

        latest_date_subquery = (
            ProductAnalytics.objects.filter(
                product__shop=shop, created_at__lt=start_date, product_id=OuterRef("product_id")
            )
            .order_by("-created_at")
            .values("date_pretty")[:1]
        )

        day_before_analytics = ProductAnalytics.objects.filter(
            product__shop=shop, date_pretty=Subquery(latest_date_subquery)
        ).values(
            "average_purchase_price",
            "orders_amount",
            "product__product_id",
            "position_in_category",
            "available_amount",
            "reviews_amount",
            "rating",
        )

        target_analytics = list(analytics_date)

        before_analytics_dict = {i["product__product_id"]: i for i in day_before_analytics}

        for item in target_analytics:
            before_item = before_analytics_dict.get(item["product_id"], None)

            item["orders_count_yesterday"] = calculate_diff(item["orders_amount"], before_item["orders_amount"])

            item["reviews_count_yesterday"] = calculate_diff(item["reviews_amount"], before_item["reviews_amount"])

            item["rating_yesterday"] = (
                calculate_diff(item["rating"], before_item["rating"]) if before_item else item["rating"]
            )

            item["position_in_category_yesterday"] = (
                calculate_diff(item["position_in_category"], before_item["position_in_category"])
                if before_item
                else None
            )

            item["price_yesterday"] = (
                calculate_diff(item["avg_purchase_price"], before_item["average_purchase_price"])
                if before_item
                else None
            )

            item["available_amount_yesterday"] = (
                calculate_diff(item["product_available_amount"], before_item["available_amount"])
                if before_item
                else item["product_available_amount"]
            )

        # for each of orders_money, diff_orders_money, weekly_orders_money, multiply by 1000
        for item in target_analytics:
            for key in ["orders_money", "diff_orders_money", "weekly_orders_money"]:
                if item[key] is not None:
                    item[key] = round(item[key]) * 1000

        for item in target_analytics:
            for key in ["avg_purchase_price", "price_yesterday"]:
                if item[key] is not None:
                    item[key] = (round(item[key]) / 100) * 100

        final_res = target_analytics

        print("Shop Daily Sales View Time taken: ", time.time() - start)

        return final_res
    except Exception as e:
        print("Error in ShopDailySalesView: ", e)
        traceback.print_exc()
        return None


def apply_color_based_on_value(cell, min_val, max_val):
    """Apply background color based on its value."""
    try:
        value = float(cell.value)

        if value == 0:
            return

        if value >= 0:
            if max_val == 0:  # Avoid division by zero
                ratio = 0
            else:
                # Use a power function to make small differences more pronounced
                ratio = (value / max_val) ** 2.5

            # Ensure ratio is between 0 and 1
            ratio = max(0, min(1, ratio))

            # Interpolating between 255 (FF) and 170 (AA) for green
            green_value = int(255 - (85 * ratio))
            fill = PatternFill(
                start_color=f"00{green_value:02X}00", end_color=f"00{green_value:02X}00", fill_type="solid"
            )
            cell.fill = fill
        else:
            if abs(min_val) == 0:  # Avoid division by zero
                ratio = 0
            else:
                # For negative values, we'll calculate the ratio differently
                ratio = (abs(value) / abs(min_val)) ** 2.5

            # Ensure ratio is between 0 and 1
            ratio = max(0, min(1, ratio))

            # Interpolating between 255 (FF) and 210 (D2) for red
            red_value = int(255 - (45 * ratio))
            # Adding a bit of blue and green to make it pinkish, but ensuring it doesn't exceed 255
            green_blue_value = int(210 * (1 - ratio))
            fill = PatternFill(
                start_color=f"{red_value:02X}{green_blue_value:02X}{green_blue_value:02X}",
                end_color=f"{red_value:02X}{green_blue_value:02X}{green_blue_value:02X}",
                fill_type="solid",
            )
            cell.fill = fill
    except Exception as e:
        pass


def export_to_excel(shops_data, user):
    try:
        # Define the path to save the Excel file
        output = io.BytesIO()

        # Column name mapping
        column_mapping = {
            "product_id": "ID ПРОДУКТА",
            "product_title": "НАЗВАНИЕ ПРОДУКТА",
            "product_title_ru": "НАЗВАНИЕ ПРОДУКТА RU",
            "category_title": "НАЗВАНИЕ КАТЕГОРИИ",
            "category_title_ru": "НАЗВАНИЕ КАТЕГОРИИ RU",
            "orders_amount": "КОЛИЧЕСТВО ЗАКАЗОВ",
            "product_available_amount": "ДОСТУПНОЕ КОЛИЧЕСТВО ПРОДУКТОВ",
            "reviews_amount": "КОЛИЧЕСТВО ОТЗЫВОВ",
            "rating": "РЕЙТИНГ",
            "position_in_category": "ПОЗИЦИЯ В КАТЕГОРИИ",
            "avg_purchase_price": "СРЕДНЯЯ ЦЕНА",
            # orders_money: total revenue общая выручка
            "orders_money": "ОБЩАЯ ВЫРУЧКА",
            "diff_orders_amount": "КОЛИЧЕСТВЕ ЗАКАЗОВ (30 ДНЕЙ)",
            "diff_reviews_amount": "КОЛИЧЕСТВЕ ОТЗЫВОВ (30 ДНЕЙ)",
            "diff_orders_money": "ОБЩАЯ ВЫРУЧКА (30 ДНЕЙ)",
            "weekly_orders_money": "ЕЖЕНЕДЕЛЬНАЯ ВЫРУЧКА",
            "weekly_orders_amount": "ЕЖЕНЕДЕЛЬНОЕ КОЛИЧЕСТВО ЗАКАЗОВ",
            "weekly_reviews_amount": "ЕЖЕНЕДЕЛЬНОЕ КОЛИЧЕСТВО ОТЗЫВОВ",
            "orders_count_yesterday": "КОЛИЧЕСТВО ЗАКАЗОВ ВЧЕРА",
            "reviews_count_yesterday": "КОЛИЧЕСТВО ОТЗЫВОВ ВЧЕРА",
            "rating_yesterday": "ИЗМЕНЕНИЕ РЕЙТИНГА ВЧЕРА",
            "position_in_category_yesterday": "ИЗМЕНЕНИЕ ПОЗИЦИИ В КАТЕГОРИИ ВЧЕРА",
            "price_yesterday": "ИЗМЕНЕНИЕ ЦЕНЫ ВЧЕРА",
            "available_amount_yesterday": "ИЗМЕНЕНИЕ ДОСТУПНОГО КОЛИЧЕСТВА ВЧЕРА",
        }

        shop_column_mapping = {
            "total_products": "КОЛИЧЕСТВО ПРОДУКТОВ",
            "total_orders": "КОЛИЧЕСТВО ЗАКАЗОВ",
            "total_revenue": "ОБЩАЯ ВЫРУЧКА",
            "total_reviews": "КОЛИЧЕСТВО ОТЗЫВОВ",
            "average_purchase_price": "СРЕДНЯЯ ЦЕНА ПРОДУКТА",
            "rating": "РЕЙТИНГ",
            # Позиция на основе дохода
            "position": "ПОЗИЦИЯ",
            "categories": "КОЛИЧЕСТВО КАТЕГОРИЙ",
        }

        # Create a new Excel writer object
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            for shop_name, data in shops_data.items():
                # Convert shop analytics to a pandas DataFrame
                shop_df = pd.DataFrame([data["shop_analytics"]])

                shop_df.rename(columns=shop_column_mapping, inplace=True)

                # Convert products analytics to a pandas DataFrame
                products_df = pd.DataFrame(data["products_analytics_of_shop"])

                # Rename columns
                products_df.rename(columns=column_mapping, inplace=True)

                # Write data to Excel
                valid_sheet_name = (
                    shop_name[:31]
                    .replace(":", "")
                    .replace("\\", "")
                    .replace("/", "")
                    .replace("?", "")
                    .replace("*", "")
                    .replace("[", "")
                    .replace("]", "")
                )
                shop_df.to_excel(writer, sheet_name=valid_sheet_name, startrow=0, index=False)
                products_df.to_excel(writer, sheet_name=valid_sheet_name, startrow=len(shop_df) + 2, index=False)

                # Apply styling using openpyxl
                ws = writer.sheets[valid_sheet_name]
                for column in ws.columns:
                    max_length = 0
                    column = [cell for cell in column]
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(cell.value)
                            cell.font = Font(size=12)
                        except Exception as e:
                            pass
                    adjusted_width = max_length + 2
                    ws.column_dimensions[column[0].column_letter].width = adjusted_width

                for row in ws.iter_rows():
                    ws.row_dimensions[row[0].row].height = 20

                # Apply conditional formatting for columns with numbers
                for col in ws.columns:
                    col_values = [
                        cell.value for cell in col if cell.value is not None and isinstance(cell.value, (int, float))
                    ]
                    if col_values:
                        min_val, max_val = min(col_values), max(col_values)
                        for cell in col:
                            if cell.column_letter != "A":  # Assuming product_id is in the first column
                                apply_color_based_on_value(cell, min_val, max_val)

                # Apply borders to all cells
                thin_border = Border(
                    left=Side(style="thin"),
                    right=Side(style="thin"),
                    top=Side(style="thin"),
                    bottom=Side(style="thin"),
                )
                for row in ws.iter_rows():
                    for cell in row:
                        cell.border = thin_border

        # Reset the stream position to the beginning
        output.seek(0)

        return output
    except Exception as e:
        print("Error in export_to_excel: ", e)
        return None


def send_reports_to_all():
    try:
        users = User.objects.filter(is_telegram_connected=True)

        for user in users:
            # Generate the report for the user
            favourite_shops = user.favourite_shops.all()
            favourite_products = user.favourite_products.all()

            all_shop_data = {}

            for shop in favourite_shops:
                # Fetch the latest analytics for the shop
                latest_analytics = ShopAnalytics.objects.filter(shop=shop).order_by("-created_at").first()

                # Convert the ShopAnalytics object to a dictionary
                shop_analytics_dict = {
                    "total_products": latest_analytics.total_products,
                    "total_orders": latest_analytics.total_orders,
                    "total_revenue": latest_analytics.total_revenue,
                    "total_reviews": latest_analytics.total_reviews,
                    "average_purchase_price": latest_analytics.average_purchase_price,
                    "rating": latest_analytics.rating,
                    "position": latest_analytics.position,
                    "categories": latest_analytics.categories.all().count(),
                }

                # Fetch the daily product analytics for the shop
                shop_data = prepare_shop_statistics(user, shop)

                all_shop_data[shop.title] = {
                    "shop_analytics": shop_analytics_dict,
                    "products_analytics_of_shop": shop_data,
                }

            # Export the combined shop data to Excel
            file_path = export_to_excel(all_shop_data, user)

            send_file_to_telegram_bot(user.telegram_chat_id, file_path)

    except Exception as e:
        print("Error in UserDailyReport: ", e)
        return None


def send_file_to_telegram_bot(chat_id, file_stream):
    bot_token = "6419033506:AAETG8prNWtydbqFEdiiFa-z_YxRaRSbzA8"
    send_document_url = f"https://api.telegram.org/bot{bot_token}/sendDocument"

    data = {"chat_id": int(chat_id), "caption": "Here is your daily report."}
    files = {
        "document": (
            f"report-{chat_id}.xlsx",
            file_stream,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
    }
    response = requests.post(send_document_url, data=data, files=files)
    return response.json()


def send_to_single_user(user):
    try:
        # Generate the report for the user
        favourite_shops = user.favourite_shops.all()
        favourite_products = user.favourite_products.all()

        all_shop_data = {}

        for shop in favourite_shops:
            # Fetch the latest analytics for the shop
            latest_analytics = ShopAnalytics.objects.filter(shop=shop).order_by("-created_at").first()

            # Convert the ShopAnalytics object to a dictionary
            shop_analytics_dict = {
                "total_products": latest_analytics.total_products,
                "total_orders": latest_analytics.total_orders,
                "total_revenue": latest_analytics.total_revenue,
                "total_reviews": latest_analytics.total_reviews,
                "average_purchase_price": latest_analytics.average_purchase_price,
                "average_order_price": latest_analytics.average_order_price,
                "rating": latest_analytics.rating,
                "position": latest_analytics.position,
                "date_pretty": latest_analytics.date_pretty,
            }

            # Fetch the daily product analytics for the shop
            shop_data = prepare_shop_statistics(user, shop)

            all_shop_data[shop.title] = {
                "shop_analytics": shop_analytics_dict,
                "products_analytics_of_shop": shop_data,
            }

        # Export the combined shop data to Excel
        file_path = export_to_excel(all_shop_data, user)
        send_file_to_telegram_bot(user.telegram_chat_id, file_path)

    except Exception as e:
        print("Error in Sending to single user: ", e)
        return None
