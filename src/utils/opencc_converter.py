from opencc import OpenCC

# s2twp：簡體 -> 繁體（台灣用語，含慣用詞彙轉換）
_converter = OpenCC("s2twp")


def to_traditional_chinese(text: str) -> str:
    return _converter.convert(text)
