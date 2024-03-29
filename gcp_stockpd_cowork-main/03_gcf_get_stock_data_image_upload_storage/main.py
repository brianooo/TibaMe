import yfinance as yf
import pandas as pd
from google.cloud import storage
import mpl_finance as mpf
import matplotlib.pyplot as plt
from os import path, remove
#from datetime import date

# Root path on CF will be /workspace, while on local Windows: C:\
root = path.dirname(path.abspath(__file__))

def hello_world(request):    
    stock_list = ['2303', '2317', '2327', '2330', '2345', '2377', '2395', '2409', '2454', '3037', '3481', '3532', '6415', '8046']
    startDate = '2014-01-01'
    #today = date.today()

    def upload_storage_doc(source, dstfile, bucketname):
        try:
          client = storage.Client()
          bucket = client.bucket(bucketname)
          blob = bucket.blob(dstfile)
          blob.upload_from_string(source)
        except:
          print(f'file upload to {bucketname} fail ..')

    def upload_storage_img(source, dstfile, bucketname):
        try:
          client = storage.Client()
          bucket = client.bucket(bucketname)
          blob = bucket.blob(dstfile)
          blob.upload_from_filename(source)
        except:
          print(f'image upload to {bucketname} fail ..')
    
    def plot_Kbar(data):
        df = data

        fig = plt.figure(figsize=(12,6))  # 設定畫布大小(橫,直)
        ax = fig.add_subplot(1,1,1) # 等份切割畫布(直向,橫向,指定圖要放的位置) 假設切割成(2,3,1) 意指切成如2x3的陣列 位置編號[[1,2,3],[4,5,6]] 圖放在1號位置
        ax.set_xticks(range(0,len(df.index),30)) # 設定刻度 此為每30筆資料為一格
        #把日期後的時間刪掉(原始:2022-05-03 00:00:00) 只剩日期(2022-05-03) 由於資料量很多所有日期都顯示會擠在一起 所以只顯示每30天的日期
        convert_date = pd.DataFrame(df.index[::30])["Date"].apply(lambda x: x.strftime("%Y-%m-%d"))
        ax.set_xticklabels(convert_date, fontsize = 12) # x座標名稱
        # 繪製k線圖或稱蠟燭圖 主體(粗)端點代表開盤與收盤價 引線(細)的端點代表最高或最低
        # width 主體寬度  alpha 透明度  在台灣紅色(俗稱上漲 colorup="r")的由上到下:高收開低 綠色(下跌 color="g"):高開收低 (美國顏色相反)
        mpf.candlestick2_ochl(ax,df["Open"],df["Close"],df["High"],df["Low"],width = 0.6, colorup = "r", colordown = "g", alpha = 0.9)
        # 另有參數 rotation = 90 表刻度文字旋轉90度
        return fig

    for stockid in stock_list:
        #stockid = stockid.strip()
        data = yf.download(f'{stockid}.Tw', startDate)
        data.drop('Adj Close', axis=1, inplace=True)
        csvfile = data.to_csv()
        print(f'Load {stockid} data done')

        upload_storage_doc(csvfile, f'stock-data/{stockid}.csv', 'your bucket name')
        print(f'Upload {stockid} data to storage done')

        fig = plot_Kbar(data[-100:])
        
        file_path = '/tmp/' + f'{stockid}.png'
        file_path = path.join(root, file_path)

        fig.savefig(file_path)
        plt.close(fig)
        # If file is a binary, we rather use 'wb' instead of 'w'
        #with open(file_path, 'wb') as file:
        #  file.write(fig)
        
        upload_storage_img(file_path, f'stock-image/{stockid}.png', 'your bucket name')
        print(f'Upload {stockid} image to storage done')
        remove(file_path)
