import sqlite3

class TrendEngine:
    def __init__(self, db_file):
        self.db_file = db_file
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_file)

    def get_monthly_metrics(self):
        query = '''
            SELECT
                strftime('%Y-%m', "Order Date") AS month,
                SUM("Sales") AS total_sales,
                SUM("Profit") AS total_profit
            FROM sales
            GROUP BY month
            ORDER BY month
        '''
        cursor = self.conn.cursor()
        cursor.execute(query)
        return cursor.fetchall()

    def calculate_growth(self, monthly_data):
        growth_data = []
        previous_sales = None
        for month, sales, profit in monthly_data:
            if previous_sales is None:
                growth = None
            else:
                growth = round(((sales - previous_sales) / previous_sales) * 100, 2)
            growth_data.append((month, sales, profit, growth))
            previous_sales = sales
        return growth_data

    def calculate_moving_average(self, monthly_data, window=3):
        moving_data = []
        sales_window = []
        for month, sales, profit in monthly_data:
            sales_window.append(sales)
            if len(sales_window) < window:
                moving_average = None
            else:
                moving_average = round(sum(sales_window) / window, 2)
                sales_window.pop(0)
            moving_data.append((month, sales, moving_average))
        return moving_data
