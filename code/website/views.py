from django.shortcuts import render
from django.http import HttpResponse
from django.http import JsonResponse
from django.conf import settings
import os
import requests
from ipware.ip import get_ip
import time
import codecs
import json
import io

try:
    from .processing import *
except:
    from processing import *

try:
    from .processing.processing import *
except:
    from processing.processing import *

from django.views.decorators.csrf import csrf_exempt
import traceback

project_folder_path = "/home/ubuntu/CanLink/code"      # for the server
# project_folder_path = "/Users/maharshmellow/Google Drive/Code/Github/CanLink/code"      # for local development


def index(request):
    return render(request, "website/header.html")


def thesisSubmission(request):
    # called when the presses the submit button after pasting the records
    if request.method == 'POST':
        if request.is_ajax():
            if len(request.FILES) != 0:
                # a file was uploaded
                file = request.FILES["records_file"].read()

                for enc in ["cp1252", "utf-8"]:
                    try:
                        raw_records = file.decode(enc)
                        break
                    except:
                        continue

                    return(HttpResponse(json.dumps({"status":1, "errors":["Error processing file - Please make sure it is in proper MARC format"], "submissions":[], "total_records": 0})))

            else:
                # copy and paste
                raw_records = request.POST.get("records")

            # recaptcha_response = request.POST.get("recaptcha")
            user_ip = get_ip(request)

            # convert js true/false to python True/False
            if request.POST.get("lac") == "false":
                lac_upload = False
            else:
                lac_upload = True


            # print(recaptcha_response, raw_records, user_ip)

            # if validateRecaptcha(recaptcha_response, user_ip):
            #     # process the records
            #     processRecords(raw_records)
            #     return HttpResponse("1")
            # else:
            #     return HttpResponse("0")

            return_values = processRecords(raw_records, lac_upload)

            return(HttpResponse(json.dumps(return_values)))     # success

    if request.method == "GET":
        return(render(request, "website/thesisSubmission.html"))
    return HttpResponse("Server Error")


def validateRecaptcha(recaptcha_response, user_ip):
    data = {
        'secret': settings.RECAPTCHA_SECRET,
        'response': recaptcha_response,
        'remoteip': user_ip
    }

    r = requests.post('https://www.google.com/recaptcha/api/siteverify', data=data)
    result = r.json()

    if result['success']:
        print("Validation Successful")
        return(True)
    else:
        print(result)
        return(False)


def processRecords(raw_records, lac_upload, silent_output=False):
    # try out the common encoding types
    encoding = ""
    for enc in ["cp1252", "utf-8"]:
        try:
            records_file = io.BytesIO(raw_records.encode(enc))
            encoding = enc
            break
        except:
            continue
        # if the program comes to this point, then the encoding was not utf-8 or cp1252
        return({"status":1, "errors":["Error processing file - Please make sure it is in proper MARC format in UTF-8 Encoding"], "submissions":[], "total_records": 0})

    try:
        # set all environment variables
        subprocess.call(["./home/ubuntu/passWords.sh"], shell=True)
        # process the records
        response = process(records_file, lac_upload, silent_output)
    except Exception as e:
        # save file locally
        error_file_name = saveErrorFile(raw_records.encode(encoding), silent_output)
        # submit github issue
        python_stacktrace = traceback.format_exc()
        title = "Error Processing File"
        body = "File: " + error_file_name + "\nPython Stacktrace:\n\n" + python_stacktrace
        label = "BUG"
        submitGithubIssue(title, body, label, silent_output=False)

        # there was some type of error processing the file
        return({"status":1, "errors":["Error processing file - Please make sure it is in proper MARC format"], "submissions":[], "total_records": 0})

    status = 1      # 1 = recaptcha successful
    errors = response[0]
    submissions = response[1]
    total_records = response[2]

    return_response = {"status":status, "errors":errors, "submissions":submissions, "total_records": total_records}

    return(return_response)

@csrf_exempt
def updateUri(request):
    if request.method == "POST":
        response = json.loads(request.body.decode('utf-8'))
        # only check for comments created/edited in an open issue
        if response["action"] == "deleted" or response["issue"]["state"] == "closed":
            return HttpResponse(1)

        issue_title = response["issue"]["title"]
        issue = response["issue"]["body"]
        issue_number = response["issue"]["number"]
        comment = response["comment"]["body"]

        if comment[0] == ">":
            # this means that the issue was generated by our program and not the person - skip it
            return HttpResponse(1)

        elif issue_title == "Missing University URL":
            # take the university name from the issue and not the comment
            # so we don't need to worry about spelling mistakes
            university_name = issue.split("The URI for **")[1].split("** could not be found")[0].strip()
            university_uri = comment.strip()
            record_file = issue.split("Record File: ")[1].strip()
            print(response)

            # check if the university uri is in the proper format
            if "http" not in university_uri or len(university_uri.split()) != 1:
                createComment(issue_number, "> Invalid URI\n> Example: http://dbpedia.org/resource/University_of_Alberta")
                return HttpResponse(1)

            print(university_name)
            print(university_uri)
            print(record_file)

            # add the new uri to the universities.pickle file
            with open(project_folder_path + "/website/processing/files/universities.pickle", "rb") as handle:
                testing_universities = pickle.load(handle)

            testing_universities[university_name] = university_uri

            with open(project_folder_path + "/website/processing/files/universities.pickle", "wb") as handle:
                pickle.dump(testing_universities, handle, protocol=pickle.HIGHEST_PROTOCOL)
                print("Saved:", university_name, university_uri)

            # reprocess the file
            with open(project_folder_path + "/website/processing/errors/"+record_file, "rb") as error_file:
                data = error_file.read()

                for enc in ["cp1252", "utf-8"]:
                    try:
                        raw_records = data.decode(enc)
                        processRecords(raw_records, False, silent_output=True)
                        break
                    except:
                        continue
            print("fixed university")
            createComment(issue_number, "> University has been updated in the records\n> Closing Issue")
            closeIssue(issue_number)
            removeFile(project_folder_path + "/website/processing/errors/"+record_file)

        elif issue_title == "Missing Degree URL":

            # check if the comment is in the proper format
            if len(comment.split()) != 2 or "http" not in comment.split()[1]:
                createComment(issue_number, "> Invalid Format\n> Example: MSc http://purl.org/ontology/bibo/degrees/ms")
                return HttpResponse(1)


            degree_name = issue.split("The URI for **")[1].split("** could not be found")[0].strip()
            degree_label, degree_uri = comment.split()
            record_file = issue.split("Record File: ")[1].strip()

            degree_name = ''.join([i for i in degree_name if i.isalpha()]).lower()
            print(degree_name)
            print(degree_uri)
            print(record_file)

            # save the new degree
            with open(project_folder_path + "/website/processing/files/degrees.pickle", "rb") as handle:
                testing_degrees = pickle.load(handle)

            if degree_name not in testing_degrees:
                testing_degrees[degree_name] = [degree_label, degree_uri]

                with open(project_folder_path + "/website/processing/files/degrees.pickle", "wb") as handle:
                    pickle.dump(testing_degrees, handle, protocol=pickle.HIGHEST_PROTOCOL)
                    print("Saved:", degree_name, degree_uri)

            # reprocess the file
            try:
                with open(project_folder_path + "/website/processing/errors/"+record_file, "rb") as error_file:
                    data = error_file.read()

                    for enc in ["cp1252", "utf-8"]:
                        try:
                            raw_records = data.decode(enc)
                            processRecords(raw_records, False, silent_output=True)
                            break
                        except:
                            continue
            except:
                # if there is an error finding the file, that means the issue has been solved already so we can just close the issue
                pass

            print("fixed degree")
            createComment(issue_number, "> Degree has been updated in the records\n> Closing Issue")
            closeIssue(issue_number)
            removeFile(project_folder_path + "/website/processing/errors/"+record_file)
        return HttpResponse(1)

def createComment(issue_number, body):
    try:
        access_token = os.environ.get("GITHUB_TOKEN")
        r = requests.post("https://api.github.com/repos/cldi/CanLink/issues/"+str(issue_number)+"/comments?access_token=" + access_token, json = {"body":body.strip()})

    except Exception as e:
        print("Created Comment", body)
        # print(traceback.format_exc())

def closeIssue(issue_number):
    try:
        access_token = os.environ.get("GITHUB_TOKEN")
        r = requests.patch("https://api.github.com/repos/cldi/CanLink/issues/"+str(issue_number)+"?access_token=" + access_token, json = {"state":"closed"})

    except Exception as e:
        print("Closed Issue", issue_number)
        # print(traceback.format_exc())

def removeFile(file_location):
    try:
        os.remove(file_location)
        print("Removed File: ", file_location)
    except Exception as e:
        print(traceback.format_exc())
        return False
    return True
