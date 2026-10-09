import pyarrow as pa


def assert_same(left, right):
    """Точное сравнение схемы и всех ячеек средствами Arrow, без медленного цикла Python."""
    assert left.shape == right.shape
    assert list(left.columns) == list(right.columns)
    assert list(left.dtypes.astype(str)) == list(right.dtypes.astype(str))
    a = pa.Table.from_pandas(left, preserve_index=False)
    b = pa.Table.from_pandas(right, preserve_index=False)
    assert a.equals(b), "Таблицы различаются по значениям или порядку строк"
