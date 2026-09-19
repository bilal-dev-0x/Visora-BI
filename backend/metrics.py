import sqlite3

class MetricsEngine:
    def __init__(self, db_file):
        self.db_file = db_file
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_file)

    def get_sum(self, column):
        cursor = self.conn.cursor()
        cursor.execute(f'SELECT SUM("{column}") FROM sales')
        return cursor.fetchone()[0]

    def get_average(self, column):
        cursor = self.conn.cursor()
        cursor.execute(f'SELECT AVG("{column}") FROM sales')
        return cursor.fetchone()[0]

    def get_grouped_metric(self, group_column, metric_column, aggregation):
        allowed_aggregations = ["SUM", "AVG", "MIN", "MAX", "COUNT"]
        if aggregation not in allowed_aggregations:
            raise ValueError("Unsupported aggregation")

        query = f'''
            SELECT "{group_column}", {aggregation}("{metric_column}")
            FROM sales
            GROUP BY "{group_column}"
        '''
        cursor = self.conn.cursor()
        cursor.execute(query)
        return cursor.fetchall()