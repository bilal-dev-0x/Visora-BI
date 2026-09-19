import sqlite3

class ContributionAnalyzer:
    def __init__(self, db_file):
        self.db_file = db_file
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_file)

    def analyze(self, dimension, metric):
        total_query = f'SELECT SUM("{metric}") FROM sales'
        grouped_query = f'''
            SELECT "{dimension}", SUM("{metric}") AS metric_value
            FROM sales
            GROUP BY "{dimension}"
            ORDER BY metric_value DESC
        '''

        cursor = self.conn.cursor()
        cursor.execute(total_query)
        total = cursor.fetchone()[0]

        if total is None or total == 0:
            return []

        cursor.execute(grouped_query)
        rows = cursor.fetchall()

        return [
            (
                dimension_value,
                metric_value,
                round((metric_value / total) * 100, 2)
            )
            for dimension_value, metric_value in rows
        ]