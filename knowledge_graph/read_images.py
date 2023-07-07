import os
from paddleocr import PaddleOCR

os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

# Paddleocr目前支持的多语言语种可以通过修改lang参数进行切换
# 例如`ch`, `en`, `fr`, `german`, `korean`, `japan`
ocr = PaddleOCR(use_angle_cls=True, lang="ch")  # need to run only once to download and load model into memory


def image2text(image_path):
    """
    从图片中提取文字
    :param image_path: 目标图片路径，一般放在本项目的temp目录下
    :return:
    """
    ocr_result = ocr.ocr(image_path, cls=True)
    result = ''
    for item in ocr_result[0]:
        # if not item[1][0].isalpha():
        result += item[1][0] + ' '
    return result.strip()
