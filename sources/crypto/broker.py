"""
    Using this module to create a wrapper class around the coinbase API calls
"""

import os, requests, sys, json 
from coinbase.rest import RESTClient
import pandas as pd
import datetime
 
class CoinbaseBroker: 
    def __init__(self, api_key, api_secret):
        self.COINBASE_API_KEY = api_key
        self.COINBASE_SECRET = api_secret

        self.watchlist = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD"]
        self.client = RESTClient(api_key, api_secret)
     # Add all additional currencies within your portfolio into the watchlist
        


    def get_candles(self, currency_pairs: 'list[str]'=None, watchlist: bool=True) -> pd.DataFrame:
        """
            Get the candlestick data (OHCLV) for various currency pairs
        """
        candles = self.client.get_products()

        #candlesticks = self.client.get_candles()
        data = []
        currtime = datetime.datetime.now()
        if watchlist: # Pull data for only those currency pairs in the self.watchlist 
            for obj in candles.products:
                if obj.product_id in self.watchlist:
                    data.append((obj.product_id, obj.base_name, obj.price, obj.price_percentage_change_24h, obj.volume_24h, obj.volume_percentage_change_24h, currtime))
        elif currency_pairs:
            for obj in candles.products:
                if obj.product_id in currency_pairs:
                    data.append((obj.product_id, obj.base_name, obj.price, obj.price_percentage_change_24h, obj.volume_24h, obj.volume_percentage_change_24h, currtime))
        else:
            for obj in candles.products:
                data.append((obj.product_id, obj.base_name, obj.price, obj.price_percentage_change_24h, obj.volume_24h, obj.volume_percentage_change_24h, currtime))
     # Create the dataframe containing all OHCLV data
        return pd.DataFrame(data, columns=['Product ID', 'Name', 'Price', 'Price Delta 24H', 'Volume 24H', 'Volume Delta 24H', 'Timestamp'])


    def get_portfolio(self):
        """
            Get your current portfolio 
        """
        account_info = self.client.get_accounts()

     # Grab your account data, such as portfolio amounts and all invested currencies
        for accounts in account_info.accounts:
            value = float(accounts.available_balance["value"])
            currency = accounts.available_balance["currency"]
            if value > 0:
                print(f"Account name: {accounts.name}; Currency: {accounts.currency}; Balance (Value): {value}; Currency: {currency}")
                self.watchlist.append(accounts.currency + "-USD")


    def manual_api_call(self):
        """
            [DEPRECATED]
            
            This method calls the coinbase API directly without using the coinbase-advanced-py library
        """
     # Make a call using a simple endpoint
        #url = "https://api.exchange.coinbase.com/"
        url = "https://api.coinbase.com/"
        account_endpoint = "v2/accounts/"
        headers = {
            'CB-ACCESS-KEY': self.COINBASE_API_KEY,
            'Accept': 'application/json'
        }
