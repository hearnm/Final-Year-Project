import datetime
import os
import sqlite3
import time
from hashlib import md5

from flask import Flask, render_template, request, \
    redirect, flash, session
from flask_login import LoginManager, current_user, UserMixin, login_user, logout_user
from livereload import Server
from matplotlib.figure import Figure


def create_app():
    app = Flask(__name__)
    app.root_path = app.root_path
    app.secret_key = os.urandom(12)

    return app


app = create_app()
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'users.login'


def get_app():
    return app


class User(UserMixin):
    app = get_app()

    def __init__(self, username):
        self.username = username

    def get_id(self):
        return self.username


@login_manager.user_loader
def get_user(username):
    return User(username)


def get_username_safe():
    if current_user.is_authenticated:
        return current_user.get_id()
    else:
        return


# Can possible use variables to merge these all together
@app.route('/')
def index():
    if current_user.is_authenticated:
        return render_template("main_upload.html", user=get_username_safe(), title="Main - Data Analysis Tool")

    else:
        return render_template("loginpage.html")


@app.route('/database')
def dbView():
    if current_user.is_authenticated:
        return render_template("db_upload.html", user=get_username_safe(),
                               title="Upload (Database) - Data Analysis Tool")

    else:
        return redirect("/")


@app.route('/guest')
def guestMode():
    return render_template("main_upload.html", title="Main - Data Analysis Tool")


@app.route('/doGraph', methods=['POST', 'GET'])
def load_graph_data():
    try:
        file = request.files["dataUpload"]
        nodeNums = list(map(int, request.form.get("nodeNumber").split(",")))
        dataTypes = request.form.getlist("chartDataSelector")
        dt1 = ""
        dt2 = None
        dataTypeNum1 = -1
        dataTypeNum2 = -1
        unit1 = ""
        unit2 = None
        isMulti = len(dataTypes) == 2
        skipPlotsModulo = request.form.get("skipPlots")
        if skipPlotsModulo == '':
            skipPlotsModulo = 1
        else:
            skipPlotsModulo = int(skipPlotsModulo) + 1

        if len(dataTypes) >= 1:
            dt1 = dataTypes[0]
            if dt1 == "Temperature":
                dataTypeNum1 = 4
                unit1 = u'\N{DEGREE SIGN}' + "C"
            elif dt1 == "Humidity":
                dataTypeNum1 = 5
                unit1 = "% RH"
            elif dt1 == "Air Pressure":
                dataTypeNum1 = 6
                unit1 = "mB"
            elif dt1 == "Luminosity":
                dataTypeNum1 = 8
                unit1 = "dBm"

            if isMulti:
                dt2 = dataTypes[1]
                if dt2 == "Temperature":
                    dataTypeNum2 = 4
                    unit2 = u'\N{DEGREE SIGN}' + "C"
                elif dt2 == "Humidity":
                    dataTypeNum2 = 5
                    unit2 = "% RH"
                elif dt2 == "Air Pressure":
                    dataTypeNum2 = 6
                    unit2 = "mB"
                elif dt2 == "Luminosity":
                    dataTypeNum2 = 8
                    unit2 = "dBm"

        data_list = []
        data_list_secondary = []
        minDate = float("inf")
        maxDate = 0
        countlines = 0
        for line in file:
            countlines += 1
            if countlines % skipPlotsModulo == 0:
                dataInfo = str(line).strip("\n").split(",")
                nodeID = int(dataInfo[1])
                if nodeID in nodeNums:
                    date = int(str(dataInfo[0]).strip("b'"))

                    if date > maxDate:
                        maxDate = date

                    if date < minDate:
                        minDate = date

                    date = date / 1000000
                    data_list.append({"node": nodeID, "x": date, "y": float(dataInfo[dataTypeNum1])})
                    if isMulti:
                        data_list_secondary.append({"node": nodeID, "x": date, "y": float(dataInfo[dataTypeNum2])})

        metadata = {
            "yAxis1Label": dt1,
            "yAxis2Label": dt2,
            "yAxis1Unit": unit1,
            "yAxis2Unit": unit2
        }

        maxDateFormatted = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(maxDate / 1000000000))
        minDateFormatted = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(minDate / 1000000000))

        dictionary = {"data1": data_list, "data2": data_list_secondary, "metadata": metadata, "nodes": nodeNums}

        return render_template("interface_graph.html", data=dictionary, dateRange=(minDateFormatted, maxDateFormatted),
                               user=get_username_safe())

    except Exception as e:
        information = ""
        if type(e) == ValueError:  # This information is safe to present to the user
            information = "This occurred on data entry line: " + str(",".join(dataInfo))
        return render_template("main_upload.html",
                               error="Oops, an error occurred. This is likely due to an erroneous piece of data in the table. " + information)


@app.route('/doGraphDB', methods=['POST', 'GET'])
def getGraphDBData():
    if not current_user.is_authenticated:
        return redirect("/")

    try:
        if request.method == 'POST':
            nodeNums = list(map(int, request.form.get("nodeNumber").split(",")))
            dataTypes = request.form.getlist("chartDataSelector")
            minRange = request.form.get("dateRangeLower")
            minRange = int(time.mktime(datetime.datetime.strptime(minRange, "%Y-%m-%dT%H:%M").timetuple()) * 1000000000)
            maxRange = request.form.get("dateRangeHigher")
            maxRange = int(time.mktime(datetime.datetime.strptime(maxRange, "%Y-%m-%dT%H:%M").timetuple()) * 1000000000)
            skipPlotsModulo = request.form.get("skipPlots")
            whereClause = request.form.get("whereClause")
        else:
            data = request.data
            print(")")
        if skipPlotsModulo == '':
            skipPlotsModulo = 1
        else:
            skipPlotsModulo = int(skipPlotsModulo) + 1

        if whereClause != '':
            whereClause = " AND " + whereClause

        nodesString = "("
        for node in nodeNums:
            nodesString += str(node)
            nodesString += ", "
        nodesString = nodesString.rstrip(", ")  # Remove the last comma if placed
        nodesString += ")"

        isMulti = len(dataTypes) > 1

        if isMulti:
            statement = "SELECT dateTime, nodeID, {}, {} FROM data WHERE nodeID IN {} AND datetime > {} AND datetime < {}{}".format(
                dataTypes[0], dataTypes[1], nodesString,
                minRange,
                maxRange, whereClause)
        else:
            statement = "SELECT dateTime, nodeID, {} FROM data WHERE nodeID IN {} AND datetime > {} AND datetime < {}{}".format(
                dataTypes[0], nodesString,
                minRange,
                maxRange, whereClause)

        conn = sqlite3.connect("./database_files/users.db")
        c = conn.cursor()
        c.execute(statement)
        rows = c.fetchall()
        c.close()

        data_list = []
        data_list_secondary = []
        minDate = float("inf")
        maxDate = 0
        dt1 = dataTypes[0]
        dt2 = None
        unit1 = ""
        unit2 = None

        if dt1 == "temperature":
            dt1 = "Temperature"
            unit1 = u'\N{DEGREE SIGN}' + "C"
        elif dt1 == "humidity":
            dt1 = "Humidity"
            unit1 = "% RH"
        elif dt1 == "airPressure":
            dt1 = "Air Pressure"
            unit1 = "mB"
        elif dt1 == "lightLevel":
            dt1 = "Light Level"
            unit1 = "dBm"

        if isMulti:
            dt2 = dataTypes[1]
            if dt2 == "temperature":
                dt2 = "Temperature"
                unit2 = u'\N{DEGREE SIGN}' + "C"
            elif dt2 == "humidity":
                dt2 = "Humidity"
                unit2 = "% RH"
            elif dt2 == "airPressure":
                dt2 = "Air Pressure"
                unit2 = "mB"
            elif dt2 == "lightLevel":
                dt2 = "Light Level"
                unit2 = "dBm"

        i = 0
        for row in rows:
            i += 1
            if i % skipPlotsModulo == 0:
                date = row[0]

                if date > maxDate:
                    maxDate = date

                if date < minDate:
                    minDate = date

                date = date / 1000000
                data_list.append({"node": row[1], "x": date, "y": row[2]})
                if isMulti:
                    data_list_secondary.append({"node": row[1], "x": date, "y": row[3]})

        metadata = {
            "yAxis1Label": dt1,
            "yAxis2Label": dt2,
            "yAxis1Unit": unit1,
            "yAxis2Unit": unit2
        }

        maxDateFormatted = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(maxDate / 1000000000))
        minDateFormatted = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(minDate / 1000000000))

        dictionary = {"data1": data_list, "data2": data_list_secondary, "metadata": metadata, "nodes": nodeNums}

        return render_template("interface_graph.html", data=dictionary, dateRange=(minDateFormatted, maxDateFormatted),
                               user=get_username_safe())
    except Exception as e:
        print(e)
        return redirect("/")


@app.route('/reloadGraph', methods=['POST'])
def reloadGraph():
    data1 = request.form.get("hiddenData1")
    data2 = request.form.get("hiddenData2")
    metadata = request.form.get("hiddenDataMeta")
    minT = request.form.get("timeMin")
    maxT = request.form.get("timeMax")

    return render_template("interface_graph.html", metadata=metadata, data1=data1, data2=data2, maxT=maxT, minT=minT,
                           user=get_username_safe())


@app.route('/dbPullNewInfo', methods=['GET'])
def pullNewInfo(prevDate, columns, nodes):
    pass


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form["username"]
        password_encr = md5(request.form["password"].encode('utf-8')).hexdigest()

        if attempt_login_auth(username, password_encr):
            return redirect("/")
        else:
            flash("Username or Password incorrect")
            return render_template("loginpage.html", error="Username or Password Incorrect")
    else:
        return redirect("/")


@app.route('/logout')
def logout():
    try:
        logout_user()
        session.pop("logged_in_user")
    except KeyError:
        pass

    return redirect('/')


###

def attempt_login_auth(username, password):
    conn = sqlite3.connect("./database_files/users.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = '{username}' AND password = '{password}';".format(username=username,
                                                                                                      password=password))
    rows = c.fetchall()
    c.close()
    if (len(rows) > 0):
        login_user(User(username))
        return True
    else:
        return False


def isGuest():
    try:
        return session['active_guest'] == "True"
    except KeyError:
        return False


def create_figure(xvals, yvals, labelx, labely):
    fig = Figure()
    axis = fig.add_subplot(1, 1, 1)
    xs = xvals
    ys = yvals
    axis.plot(xs, ys)
    fig.suptitle("Graph of " + labely + " over " + labelx)
    return fig


if __name__ == '__main__':
    server = Server(app.wsgi_app)
    server.serve()
