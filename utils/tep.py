from googletrans import Translator

def translate_en_to_fa(text: str) -> str:
    """
    تابعی برای ترجمه متن انگلیسی به فارسی با دقت بالا
    """
    # بررسی خالی نبودن ورودی
    if not text or not text.strip():
        return ""

    translator = Translator()

    try:
        # ترجمه از انگلیسی (en) به فارسی (fa)
        translation = translator.translate(text, src='en', dest='fa')
        return translation.text

    except Exception as e:
        return f"خطا در برقراری ارتباط یا ترجمه: {str(e)}"
