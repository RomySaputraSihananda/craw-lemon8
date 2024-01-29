import asyncio
import requests
import re
import asyncio

from time import time
from aiohttp import ClientSession
from requests import Response
from json import dumps, loads
from concurrent.futures import ThreadPoolExecutor

from helpers import Iostream, Datetime, ConnectionS3

class BaseLemon8:
    def __init__(self, **kwargs) -> None:
        self.__s3: bool = kwargs.get('s3')
        self.__request: ClientSession = None
    
    @staticmethod
    def get_user_profile(user_id) -> dict:
        response: Response = requests.get(
            'https://api22-normal-useast1a.lemon8-app.com/api/550/user/profile/homepage',
            params={
                'user_id': user_id,
                'aid': '2657',
            },
            headers={
                'User-Agent': 'com.bd.nproject/55014 (Linux; U; Android 9; en_US; unknown; Build/PI;tt-ok/3.12.13.1)',
            },
        )

        return response.json()['data']
    
    @staticmethod
    def get_user_posts(user_id) -> dict:
        response: Response = requests.get(
            'https://api22-normal-useast1a.lemon8-app.com/api/550/stream',
            params={
                'category': '486', 
                'count': '1000', 
                'category_parameter': user_id, 
                'session_cnt': '1', 
                'aid': '2657', 
                'device_platform': 'android', 
            },
            headers={
                'User-Agent': 'com.bd.nproject/55014 (Linux; U; Android 9; en_US; unknown; Build/PI;tt-ok/3.12.13.1)',
            },
        )

        return loads(re.sub(r'<[^>]*>', '', dumps(response.json(), ensure_ascii=False)))['data']['items']

    async def __get_comments(self, post_detail: dict, user_detail: dict) -> None:
        link: str = f'https://www.lemon8-app.com/{user_detail["user_unique_name"]}/{post_detail["item_id"]}'
        link_split: list = link.split('/')

        headers: dict = {
            "link": link,
            "domain": link_split[2],
            "tag": link_split[2:],
            "crawling_time": Datetime.now(),
            "crawling_time_epoch": int(time()),
            'user_detail': user_detail,
            'post_detail': post_detail,
            "path_data_raw": f'S3://ai-pipeline-statistics/data/data_raw/data_review/lemon8/{user_detail["user_unique_name"]}/{post_detail["item_id"]}/json/detail.json',
            "path_data_clean": f'S3://ai-pipeline-statistics/data/data_clean/data_review/lemon8/{user_detail["user_unique_name"]}/{post_detail["item_id"]}/json/detail.json',
        };


        async with self.__request.get('https://api22-normal-useast1a.lemon8-app.com/api/550/comment_v2/comments',                             
                                    params={
                                        'group_id': post_detail['group_id'], 
                                        'item_id': post_detail['item_id'], 
                                        'media_id': post_detail['media_id'], 
                                        'count': '1000', 
                                        'aid': '2657', 
                                    }) as response:
            comments: dict = await response.json()

            paths: list = [path.replace('S3://ai-pipeline-statistics/', '') for path in [headers["path_data_raw"], headers["path_data_clean"]]] 

            try:
                with ThreadPoolExecutor() as executor:
                    if(self.__s3):
                        executor.map(lambda path: ConnectionS3.upload(headers, path), paths)
                    else:
                        executor.map(lambda path: Iostream.write_json(headers, path), paths)
            except Exception as e:
                raise e

        comments: list = comments['data']['data']

        log: dict = {
            "Crawlling_time": Datetime.now(),
            "id_project": None,
            "project": "Data Intelligence",
            "sub_project": "data review",
            "source_name": headers['domain'],
            "sub_source_name": user_detail["user_unique_name"],
            "id_sub_source": str(post_detail["item_id"]),
            "total_data": len(comments),
            "total_success": 0,
            "total_failed": 0,
            "status": "Process",
            "assign": "romy",
        }
        Iostream.write_log(log, name=__name__)

        if(not bool(len(comments))): 
            log['status'] = 'Done'
            return Iostream.update_log(log, name=__name__)
        
        return await asyncio.gather(*(self.__get_detail_comment(comment["id"], headers, log) for comment in comments))        

    async def __get_detail_comment(self, comment_id, headers: dict, log: dict) -> None:
        try:
            async with self.__request.get('https://api22-normal-useast1a.lemon8-app.com/api/550/comment_v2/detail',
                                    params={
                                        'group_id': headers['post_detail']['group_id'], 
                                        'item_id': headers['post_detail']['item_id'],
                                        'media_id': headers['post_detail']['media_id'], 
                                        'comment_id': comment_id, 
                                        'count': '1000', 
                                        'aid': '2657', 
                                        'language': 'en', 
                                    },
                                    ) as response:
                detail_comment = await response.json()

                data: dict = {
                    **headers, 
                    "detail_review": detail_comment['data'],
                    "path_data_raw": f'S3://ai-pipeline-statistics/data/data_raw/data_review/lemon8/{headers["user_detail"]["user_unique_name"]}/{headers["post_detail"]["item_id"]}/json/{comment_id}.json',
                    "path_data_clean": f'S3://ai-pipeline-statistics/data/data_clean/data_review/lemon8/{headers["user_detail"]["user_unique_name"]}/{headers["post_detail"]["item_id"]}/json/{comment_id}.json',
                }

                paths: list = [path.replace('S3://ai-pipeline-statistics/', '') for path in [data["path_data_raw"], data["path_data_clean"]]] 
                
                try:
                    with ThreadPoolExecutor() as executor:
                        if(self.__s3):
                            executor.map(lambda path: ConnectionS3.upload(data, path),paths)
                        else:
                            executor.map(lambda path: Iostream.write_json(data, path),paths)
                except Exception as e:
                    raise e

                Iostream.info_log(log, comment_id, 'success', name=__name__)
                
                log['total_success'] += 1
                Iostream.update_log(log, name=__name__)
        
        except Exception as e:
            Iostream.info_log(log, comment_id, 'failed', error=e, name=__name__)

            log['total_failed'] += 1
            Iostream.update_log(log, name=__name__)
        
        log['status'] = 'Done'
        Iostream.update_log(log, name=__name__)


    async def by_user_id(self, user_id) -> None:
        self.__request: ClientSession = ClientSession(headers={
            'User-Agent': 'com.bd.nproject/55014 (Linux; U; Android 9; en_US; unknown; Build/PI;tt-ok/3.12.13.1)',
        })

        user_detail: dict = self.get_user_profile(user_id)
        posts: dict = self.get_user_posts(user_id)
        await asyncio.gather(*(self.__get_comments(post, user_detail) for post in posts))

        await self.__request.close()


# testing
if(__name__ == '__main__'):
    lemon8: BaseLemon8 = BaseLemon8()

    asyncio.run(lemon8.by_user_id('7138599741986915329'))