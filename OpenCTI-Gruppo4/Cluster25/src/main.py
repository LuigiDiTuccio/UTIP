import requests
from requests.exceptions import HTTPError
from stix2 import Bundle, Identity, ExternalReference, Report, TLP_WHITE
import os
import yaml
import time
from datetime import datetime
from pycti import OpenCTIConnectorHelper, get_config_variable, SimpleObservable, OpenCTIStix2Utils
from bs4 import BeautifulSoup


class Cluster25Connector:
    def __init__(self):
        config_file_path = os.path.dirname(os.path.abspath(__file__)) + "/config.yml"
        config = (
            yaml.load(open(config_file_path), Loader=yaml.FullLoader)
            if os.path.isfile(config_file_path)
            else {}
        )
        self.helper = OpenCTIConnectorHelper(config)
        self.time_interval = get_config_variable("CLUSTER25_INTERVAL_SEC", ["cluster25", "time_interval"], config, True)

        authors = self.helper.api.identity.list(
            filters=[{"key": "name", "values": "Cluster25"}, {"key": "identity_class", "values": "organization"}])
        if authors:
            self.author = Identity(id=authors[0]['standard_id'], name="Cluster25", identity_class="organization")
        else:
            self.author = Identity(id=OpenCTIStix2Utils.generate_random_stix_id("identity"), name="Cluster25",
                                   identity_class="organization")

    def get_pdf_link(self, link):
        html_text = requests.get(link).text
        soup = BeautifulSoup(html_text, 'html.parser')
        pdf = soup.find('div',
                        class_='elementor-element elementor-element-48deb1c elementor-widget elementor-widget-image')
        if pdf:
            pdf = pdf.find('a').get('href')
        else:
            pdf = "Not found"
        return pdf
    
    def get_tags(self, link):
        html_text = requests.get(link).text
        soup = BeautifulSoup(html_text, 'html.parser')
        tags = soup.find('p', class_='firwl-tags')
        tag_list = []
        if tags is not None:
            for t in tags:
                tag_list.append(t.text.replace('Tagged as:', "").replace(',',"").replace('.',"").replace('#',"").strip())
        else:
            tags= 'No tags found'
        tag_list = [value for value in tag_list if value != ""]
        return tag_list


    def get_interval(self) -> int:
        return int(self.time_interval)

    def process_data(self) -> Bundle:
        try:
            bundleObjects = [self.author]
            html_text = requests.get("https://cluster25.io/blog/").text
            soup = BeautifulSoup(html_text, 'html.parser')
            reports = soup.find_all('div', class_='firwl-post__content')
            for report in reports:
                labels = []
                pre_link = report.find('h3', class_='firwl-post__title')
                title = pre_link.text
                pdf_link = pre_link.find('a').get('href')
                tg_list = self.get_tags(pdf_link)
                if pdf_link is not None:
                    pdf_link = self.get_pdf_link(pdf_link)
                tags = report.find('span', class_='firwl-p-catz')
                if tags:
                    for t in tags.find_all('a'):
                        labels.append(t.text.strip().replace("\t", "").replace("\n", "").replace("+", ""))

                tag_list = tg_list + labels
                date = report.find('a', class_='firwl-p-auth').text.replace("/", "").strip()
                date = datetime.strptime(date, '%B %d, %Y').strftime('%Y-%m-%dT%H:%M:%SZ')
                desc = report.find('div', class_='firwl-excerpt').text.strip()

                er = ExternalReference(
                    source_name="cluster25 " + date,
                    url=pdf_link
                )

                bundleObjects.append(Report(type="report",
                                            spec_version="2.1",
                                            id=OpenCTIStix2Utils.generate_random_stix_id("report"),
                                            created=date,
                                            name=title,
                                            description=desc,
                                            object_refs=self.author,
                                            external_references=[er],
                                            published=date,
                                            #created_by_ref=self.author,
                                            labels=tag_list
                                            ))
            bundle=bundleObjects[:-1]
            return Bundle(objects=bundle, allow_custom=True).serialize()
        except HTTPError as http_err:
            print(f'HTTP error occurred: {http_err}')
        except Exception as err:
            print(f'Other error occurred: {err}')

    def run(self) -> None:
        get_run_and_terminate = getattr(self.helper, "get_run_and_terminate", None)
        if callable(get_run_and_terminate) and self.helper.get_run_and_terminate():
            self.helper.send_stix2_bundle(self.request_data(), work_id='TEST_ID')
        else:
            while True:
                timestamp = int(time.time())
                now = datetime.utcfromtimestamp(timestamp)
                friendly_name = "CLUSTER 25 run @ " + now.strftime("%Y-%m-%d %H:%M:%S")
                work_id = self.helper.api.work.initiate_work(self.helper.connect_id, friendly_name)
                self.helper.send_stix2_bundle(self.process_data(),
                                              entities_types=self.helper.connect_scope,
                                              work_id=work_id)
                time.sleep(self.get_interval())


if __name__ == "__main__":
    try:
        cluster25_connector = Cluster25Connector()
        cluster25_connector.run()
    except Exception as e:
        print(e)
        time.sleep(10)
        exit(0)
