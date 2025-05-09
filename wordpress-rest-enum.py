#wordpress-rest-enum.py
import argparse
import json
import logging
import os
import re
import requests
from rich.console import Console
from rich.progress import Progress
import urllib3

urllib3.disable_warnings()

# Argument parsing
parser = argparse.ArgumentParser()
# Argument group, select either website or input file
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument("-w", "--website", help="Website to check.", action='store', type=str)
group.add_argument("-i", "--input-file", help="Input file containing list of websites", type=str)
parser.add_argument_group(group)
parser.add_argument("--log-level", default=logging.ERROR, type=lambda x: getattr(logging, x), help="Configure the logging level.")
parser.add_argument("-m", "--media", help="Fetch media", action=argparse.BooleanOptionalAction, required=False)
parser.add_argument("-po", "--posts", help="Fetch posts", action=argparse.BooleanOptionalAction, required=False)
parser.add_argument("-pa", "--pages", help="Fetch pages", action=argparse.BooleanOptionalAction, required=False)
parser.add_argument("-u", "--users", help="Fetch users", action=argparse.BooleanOptionalAction, required=False)
parser.add_argument("-c", "--comments", help="Fetch comments", action=argparse.BooleanOptionalAction, required=False)
parser.add_argument(
    "-im",
    "--ignoreImages",
    help="Filter out extensions commonly associated with images and video",
    action=argparse.BooleanOptionalAction,
    required=False,
)
parser.add_argument("-o", "--output-file", help="Output file to save the results.", type=str, required=False)

cliArgs = parser.parse_args()

# Logging
logging.basicConfig(level=cliArgs.log_level)

# Globals
HEADERS = {'User-Agent': 'WordPress Testing'}

# Initialize Rich Console
console = Console()

def requestRESTAPIComments(website: str, fetchPage: int, timeout=10) -> json:
    perPage = 100
    apiRequest = f'{website}/wp-json/wp/v2/comments?per_page={perPage}&page={str(fetchPage)}'
    results = []
    try:
        with requests.Session() as s:
            download = s.get(apiRequest, headers=HEADERS, verify=False, timeout=timeout)
            if download.status_code == 200:
                content = '[' + '['.join(download.text.split('[')[1:])
                comments = json.loads(content)
                for comment in comments:
                    try:
                        newComment = {"name": comment['author_name'], "date": comment['date'], "link": comment['link']}
                        results.append(newComment)
                    except Exception as err:
                        console.print(f"[red]Unexpected {err=}, {type(err)=}[/red]")
                        raise
                fetchPage = fetchPage + 1
                if len(comments) > 0:
                    results += requestRESTAPIComments(website, fetchPage)
    except:
        raise

    return results


def requestRESTAPIUsers(website: str, fetchPage: int, timeout=10) -> json:
    perPage = 100
    apiRequest = f'{website}/wp-json/wp/v2/users?per_page={perPage}&page={str(fetchPage)}'
    results = []
    try:
        with requests.Session() as s:
            download = s.get(apiRequest, headers=HEADERS, verify=False, timeout=timeout)
            if download.status_code == 200:
                content = download.text
                users = json.loads(content)
                for user in users:
                    try:
                        newUser = {"name": user['name'], "username": user['slug']}
                        results.append(newUser)
                    except Exception as err:
                        console.print(f"[red]Unexpected {err=}, {type(err)=}[/red]")
                        raise
                fetchPage = fetchPage + 1
                if len(users) > 0:
                    results += requestRESTAPIUsers(website, fetchPage)

    except:
        raise
    return results


def requestRESTAPI(type: str, website: str, fetchPage: int, timeout=10) -> list:
    perPage = 100
    results = []
    apiRequest = f'{website}/wp-json/wp/v2/{type}?per_page={perPage}&page={str(fetchPage)}'
    
    try:
        with requests.Session() as s:
            response = s.get(apiRequest, headers=HEADERS, verify=False, timeout=timeout)
            
            if response.status_code == 200:
                # Check if the response is empty
                if not response.text.strip():  # If response body is empty
                    logging.warning(f"Empty response from {website} for {type} endpoint")
                    return results  # Return empty results as no data

                try:
                    content = response.json()  # Try to parse JSON response
                    if content:
                        for item in content:
                            try:
                                results.append(item['guid']['rendered'])
                            except KeyError as e:
                                logging.warning(f"Unexpected structure in response for {website}: {e}")
                    else:
                        logging.warning(f"No content found in response from {website} for {type} endpoint")
                
                except json.JSONDecodeError as e:
                    logging.warning(f"JSON decode error for {website}: {e}. Response content: {response.text}")
                    # Handle the case where the response is not valid JSON
                    return results  # Return empty results if JSON decoding fails
            else:
                logging.warning(f"Request failed for {website}: Status Code {response.status_code}")
    except requests.exceptions.RequestException as e:
        logging.warning(f"Error during request to {website}: {e}")

    return results


def main():
    websites = []
    if cliArgs.input_file:
        with open(cliArgs.input_file, 'r') as f:
            websites = [line.strip() for line in f if line.strip()]
    else:
        websites.append(cliArgs.website)

    fetchPage = 1
    cnt = 0
    progress_data = []  # To keep track of progress

    try:
        with Progress(console=console) as progress:
            task = progress.add_task("[cyan]Enumerating sites...", total=len(websites))

            for website in websites:
                result = {"website": website}
                found = False

                if cliArgs.posts:
                    result["posts"] = requestRESTAPI("posts", website, fetchPage)
                    if result["posts"]:
                        found = True

                if cliArgs.pages:
                    result["pages"] = requestRESTAPI("pages", website, fetchPage)
                    if result["pages"]:
                        found = True

                if cliArgs.comments:
                    result["comments"] = requestRESTAPIComments(website, fetchPage)
                    if result["comments"]:
                        found = True

                if cliArgs.media:
                    result["media"] = requestRESTAPI("media", website, fetchPage)
                    if cliArgs.ignoreImages:
                        result["media"] = [
                            url for url in result["media"]
                            if not re.search(r'\.(jpg|gif|jpeg|png|svg|tiff|webm|webp)$', url, re.IGNORECASE)
                        ]
                    if result["media"]:
                        found = True

                if cliArgs.users:
                    result["users"] = requestRESTAPIUsers(website, fetchPage)
                    if result["users"]:
                        found = True
                else:
                    if cliArgs.output_file:
                        with open(cliArgs.output_file, 'a', encoding='utf-8') as f:
                            if cnt > 0:
                                f.write("\n")
                            f.write(json.dumps(result, ensure_ascii=False))
                            progress_data.append(result)  # Save the result for potential resume
                    else:
                        console.print_json(json.dumps(result))

                cnt += 1
                progress.advance(task)

    except KeyboardInterrupt:
        console.print("[bold red]Interrupted by user. Saving progress...[/bold red]")
        # Save progress to output file before exiting
        if cliArgs.output_file:
            with open(cliArgs.output_file, 'a', encoding='utf-8') as f:
                for data in progress_data:
                    f.write(json.dumps(data, ensure_ascii=False) + "\n")
        console.print("[bold green]Progress saved successfully! Exiting...[/bold green]")

    except json.JSONDecodeError as e:
        console.print(f"[red]JSON decode error:[/red] {e}")
    except urllib3.exceptions.MaxRetryError as e:
        console.print(f"[red]Max retries exceeded:[/red] {e}")
    except requests.exceptions.ConnectionError as e:
        console.print(f"[red]Connection error:[/red] {e}")
    except requests.exceptions.InvalidSchema as e:
        console.print(f"[red]Invalid schema:[/red] {e}")
    except urllib3.exceptions.ReadTimeoutError as e:
        console.print(f"[red]Timeout error:[/red] {e}")
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")


if __name__ == '__main__':
    main()
