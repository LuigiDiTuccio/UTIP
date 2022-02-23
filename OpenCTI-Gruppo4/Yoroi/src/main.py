import os
import yaml
import time
from stix2 import Bundle, Identity, ExternalReference, Report
from pycti import OpenCTIConnectorHelper, get_config_variable, SimpleObservable, OpenCTIStix2Utils
from datetime import datetime
from requests.exceptions import HTTPError
from bs4 import BeautifulSoup
import requests


class YoroiConnector:
    def __init__(self):
        # Instantiate the connector helper from config
        config_file_path = os.path.dirname(os.path.abspath(__file__)) + "/config.yml"
        config = (
            yaml.load(open(config_file_path), Loader=yaml.FullLoader)
            if os.path.isfile(config_file_path)
            else {}
        )
        self.helper = OpenCTIConnectorHelper(config)
        self.time_interval = get_config_variable(
            "YOROI_INTERVAL_SEC", ["yoroi", "time_interval"], config, True
        )

        authors = self.helper.api.identity.list(
            filters=[{"key": "name", "values": "Yoroi"}, {"key": "identity_class", "values": "organization"}])
        if authors:
            self.author = Identity(id=authors[0]['standard_id'], name="Yoroi", identity_class="organization")
        else:
            self.author = Identity(id=OpenCTIStix2Utils.generate_random_stix_id("identity"), name="Yoroi",
                                   identity_class="organization")

    def get_interval(self) -> int:
        return int(self.time_interval)

    def process_data(self) -> Bundle:
        try:
            bundleObjects = [self.author]
            html_text = requests.get("https://yoroi.company/blog/").text
            soup = BeautifulSoup(html_text, 'html.parser')
            max_page = int(soup.find_all('a', class_='page-numbers')[-2].text)

            for pg in range(1, max_page+1):
                page = requests.get("https://yoroi.company/blog/page/" + str(pg) + "/").text
                soup = BeautifulSoup(page, 'html.parser')

                reports = soup.find_all('div', class_='oxy-post')
                for report in reports:
                    labels = []
                    title = report.find('h4', class_='yoroi-post__title').text
                    tags = report.find('div', class_='yoroi-post__tags')
                    for t in tags.find_all('div', class_='yoroi-post__tag'):
                        labels.append(t.text.strip())
                    date = report.find('p', class_='yoroi-post__date').text
                    date = datetime.strptime(date, '%m/%d/%Y').strftime('%Y-%m-%dT%H:%M:%SZ')
                    desc = report.find('div', class_='yoroi-post__description yoroi-post__description--collapsed').text
                    pre_link = report.find('a', class_='button button--redshadow')
                    link = str(pre_link.get('href'))

                    id = OpenCTIStix2Utils.generate_random_stix_id("report")
                    er = ExternalReference(
                        source_name="yoroi " + date, url=link
                    )

                    bundleObjects.append(Report(type="report",
                                                report_types="threat-report",
                                                spec_version="2.1",
                                                id=OpenCTIStix2Utils.generate_random_stix_id("report"),
                                                created=date,
                                                name=title,
                                                modified=date,
                                                description=desc,
                                                object_refs=[self.author],
                                                labels=labels,
                                                published=date,
                                                external_references=[er],
                                                # created_by_ref=[self.author]    
                                                ))
            return Bundle(objects=bundleObjects, allow_custom=True).serialize()
        except HTTPError as http_err:
            print(f'HTTP error occurred: {http_err}')
        except Exception as err:
            print(f'Other error occurred: {err}')

    def run(self) -> None:
        get_run_and_terminate = getattr(self.helper, "get_run_and_terminate", None)
        if callable(get_run_and_terminate) and self.helper.get_run_and_terminate():
            self.helper.send_stix2_bundle(self.process_data(), work_id='YOROI_ID')
        else:
            while True:
                timestamp = int(time.time())
                now = datetime.utcfromtimestamp(timestamp)
                friendly_name = "YOROI run @ " + now.strftime("%Y-%m-%d %H:%M:%S")
                work_id = self.helper.api.work.initiate_work(self.helper.connect_id, friendly_name)
                self.helper.send_stix2_bundle(self.process_data(),
                                              entities_types=self.helper.connect_scope,
                                              work_id=work_id)
                time.sleep(self.get_interval())


if __name__ == "__main__":
    try:
        connector = YoroiConnector()
        connector.run()

    except Exception as e:
        print(e)
        time.sleep(10)
        exit(0)

