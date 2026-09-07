import platform
import matplotlib.pyplot as plt
from matplotlib import font_manager, rc

path = '/library/Fonts/Arial Unicode.ttf'

if platform.system() == 'Darwin':
    print('Hangul OK in your MAC!')
    rc('font', family='Arial Unicode MS')
elif platform.system() == 'Windows':
    font_name = font_manager.FontProperties(fname=path).get_name()
    rc('font', family=font_name)
else:
    print('Unknown system.. sorry')

# 주석 처리된 코드 또는 코드 삭제
plt.rcParams['axes.unicode_minus'] = False