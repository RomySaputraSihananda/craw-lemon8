import asyncio
import requests
import re

from aiohttp import ClientSession
from requests import Response
from json import dumps
from time import time

from helpers import Datetime, Iostream

class BaseMicrosoftStore:
    def __init__(self) -> None:
        self.__requests: ClientSession = None 
    
    async def __get_detail(self, product_id: int) -> dict:
        async with self.__requests.get('https://microsoft-store.azurewebsites.net/api/pages/pdp', 
                                        params={
                                            'productId': product_id
                                        }) as response:

            return await response.json()
        
    async def __get_rating(self, product_id: int) -> dict: 
        async with self.__requests.get(f'https://microsoft-store.azurewebsites.net/api/Products/GetReviewsSummary/{product_id}') as response:
            return await response.json()
        
    async def __get_reviews(self, product_id: int) -> list: 
        reviews: list = []
        i: int = 1

        while(True):
            async with self.__requests.get(f'https://microsoft-store.azurewebsites.net/api/products/getReviews/{product_id}',
                                            params={
                                                'pgNo': i,
                                                'noItems': 25,
                                            }) as response:
                response_json: dict = await response.json()

                items: list = response_json['items']
                has_more_pages: bool = response_json['hasMorePages']

                reviews.extend(items)

            if (not has_more_pages): break
            i += 1

        return reviews
    
    async def __process(self, product_id: str) -> None:
        try:
            app: dict = await self.__get_detail(product_id)
            rating: dict = await self.__get_rating(product_id)
            reviews: list = await self.__get_reviews(product_id)

            link: str = f'https://microsoft-store.azurewebsites.net/detail/{app["productId"]}'
            link_split: list = link.split("/")

            title: str = app['title']

            headers: dict = {
                'link': link,
                'domain': link_split[2],
                'tag': link_split[2:],
                'crawling_time': Datetime.now(),
                'crawling_time_epoch': int(time()),
                'reviews_name': title,
                'release_date_reviews': Datetime.utc(app['releaseDateUtc']),
                'release_date_epoch_reviews': Datetime.utc_epoch(app['releaseDateUtc']),
                'description_reviews': app['description'],
                'developer_reviews': app['developerName'] if len(app['developerName']) else None,
                'publisher_reviews': app['publisherName'] if len(app['publisherName']) else None,
                'features_reviews': app['features'],
                'website_url_reviews': app['appWebsiteUrl'],
                'product_ratings_reviews': [rating['description'] for rating in app['productRatings']],
                'system_requirements_reviews': {
                    key: [
                        {
                            "name": item["name"], 
                            "description": item["description"]
                        } for item in value["items"]
                    ] for key, value in app['systemRequirements'].items()
                },
                'approximate_size_in_bytes_reviews': app['approximateSizeInBytes'],
                'maxInstall_size_in_bytes_reviews': app['maxInstallSizeInBytes'],
                'permissions_required_reviews': app['permissionsRequired'],
                'installation_reviews': app['installationTerms'],
                'allowed_platforms_reviews': app['allowedPlatforms'],
                'screenshots_reviews': [screenshot['url'] for screenshot in app['screenshots']],
                'location_reviews': None,
                'category_reviews': "application",
                'total_reviews': rating['reviewCount'],
                'review_info': {
                    key[4]: value for key, value in rating.items() if re.match(r"star\d{1}Count$", key)
                },
                'rating_info': {
                    key[4]: value for key, value in rating.items() if key.endswith("ReviewCount")
                },
                'reviews_rating': {
                    'total_rating': rating['averageRating'],
                    'detail_total_rating': None,
                },
                'path_data_raw': f'S3://ai-pipeline-statistics/data/data_raw/data_review/microsoft_store/{app["title"]}/json/detail.json',
                'path_data_clean': f'S3://ai-pipeline-statistics/data/data_clean/data_review/microsoft_store/{app["title"]}/json/detail.json',
            }

            log: dict = {
                'Crawlling_time': Datetime.now(),
                'id_project': None,
                'project': "Data Intelligence",
                'sub_project': "data review",
                'source_name': link_split[2],
                'sub_source_name': title,
                'id_sub_source': app['productId'],
                'total_data': len(reviews),
                'total_success': 0,
                'total_failed': 0,
                'status': "Process",
                'assign': "romy",
            }

            Iostream.write_log(log, name=__name__)

            for review in reviews:
                username: str = review['reviewerName']
                review_id: str = review['reviewId']
                try:
                    data: dict = {
                        'path_data_raw': f'S3://ai-pipeline-statistics/data/data_raw/data_review/microsoft_store/{title}/json/data_review/{review_id}.json',
                        'path_data_clean': f'S3://ai-pipeline-statistics/data/data_clean/data_review/microsoft_store/{title}/json/data_review/{review_id}.json',
                            'detail_reviews': {
                            'username_reviews': username,
                            'image_reviews': None,
                            'created_time': Datetime.utc(review['submittedDateTimeUtc']),
                            'created_time_epoch': Datetime.utc_epoch(review['submittedDateTimeUtc']),
                            'email_reviews': None,
                            'company_name': None,
                            'location_reviews': None,
                            'title_detail_reviews': review['title'],
                            'reviews_rating': review['rating'],
                            'detail_reviews_rating': None,
                            'total_likes_reviews': review['helpfulPositive'],
                            'total_dislikes_reviews': review['helpfulNegative'],
                            'total_reply_reviews': None,
                            'content_reviews': review['reviewText'],
                            'reply_content_reviews': None,
                            'date_of_experience': None,
                            'date_of_experience_epoch': None,
                        },
                    }

                    Iostream.info_log(log, review_id, 'success', name=__name__)

                    log['total_success'] += 1
                    Iostream.update_log(log, name=__name__)

                except Exception as e:
                    Iostream.info_log(log, review_id, 'failed', error=e, name=__name__)

                    log['total_failed'] += 1
                    Iostream.update_log(log, name=__name__)
                
            log['status'] = 'Done'
            Iostream.update_log(log, name=__name__)

        except Exception as e:
            print(e)
        
    async def _get_by_media_type(self, media_type: str):
        self.__requests: ClientSession = ClientSession()
        async with self.__requests.get('https://microsoft-store.azurewebsites.net/api/Reco/GetCollectionFiltersList', 
                                        params={
                                            'mediaType': media_type
                                        }) as response:
            response_json = await response.json()
            for choice in response_json[0]['choices']:
                choice_id: str = re.sub(r'^.', choice['choiceId'][0].upper(), choice['choiceId'])

                page: int = 1
                while(True):
                    response: Response = requests.get('https://microsoft-store.azurewebsites.net/api/Reco/GetComputedProductsList',
                        params={
                            'listName': choice_id,
                            'pgNo': page,
                            'noItems': 5,
                            'filteredCategories': "AllProducts",
                            'mediaType': media_type,
                        }
                    )
                    
                    response_json: dict = response.json()
                    
                    products_list: list = response_json['productsList']
                    if (response_json['nextPageNumber'] < 0): break

                    await asyncio.gather(*(self.__process(product['productId']) for product in products_list))
                    break

                    page += 1
                
                break

        await self.__requests.close()

    async def _get_all(self):
        for media_type in ("games", "apps"):
            await self._get_by_media_type(media_type)
        
    async def _start(self):
        self.__requests: ClientSession = ClientSession()
        print("hello")

        await self.__requests.close()


if(__name__ == '__main__'):
    microsoftStore: BaseMicrosoftStore = BaseMicrosoftStore()
    asyncio.run(microsoftStore._get_by_media_type('games'))