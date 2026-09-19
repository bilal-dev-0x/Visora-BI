import sqlite3

class AnomalyDetector:
    def __init__(self, db_file):
        self.db_file = db_file
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_file)

    def detect_z_score(self, column, threshold=2.0):
        query = f'SELECT rowid, "{column}" FROM sales WHERE "{column}" IS NOT NULL'
        cursor = self.conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        values = [float(row[1]) for row in rows]

        if len(values) < 2:
            return []

        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        standard_deviation = variance ** 0.5

        if standard_deviation == 0:
            return []

        anomalies = []
        for rowid, value in rows:
            z_score = (float(value) - mean) / standard_deviation
            if abs(z_score) >= threshold:
                anomalies.append((rowid, value, round(z_score, 2)))

        return anomalies
