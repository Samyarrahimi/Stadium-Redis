import json
import redis
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from random import randrange
from flask import Flask, request, render_template, make_response, redirect, url_for, session
from flask_restful import Api, Resource, reqparse

app = Flask(__name__, template_folder="templates")
api = Api(app)

post_parser = reqparse.RequestParser()
post_parser.add_argument("selected_class", type=str)
post_parser.add_argument("username", type=str)

ticket_count = 5000
r = redis.StrictRedis(host='localhost', port=6379)
r.mset({"A_rem": ticket_count, "B_rem": ticket_count, "C_rem": ticket_count, "D_rem": ticket_count})

now = datetime.now()
current_time = now.strftime("%H:%M:%S")
t = {"username": "tmp",
     "seat_no": 0,
     "reserve_time": current_time,
     "finalized": 1}
t = json.dumps(t)
r.set("A0", t)
r.set("B0", t)
r.set("C0", t)
r.set("D0", t)


def get_last_seat(selected_class):
    for i in range(0, ticket_count + 1):
        key = selected_class + str(i)
        if not r.exists(key):
            return i
    return -1


def clean_invalid_reservations():
    print("removing invalid reservations from DB")
    now = datetime.now()
    current_time = now.strftime("%H:%M:%S")

    for key in r.keys():
        key = key.decode("utf-8")
        if "_" not in key:
            record = json.loads(r.get(key))
            print("Current time: ", current_time)
            if record["finalized"] == 0:
                current_hour = int(current_time[0] + current_time[1])
                current_minute = int(current_time[3] + current_time[4])
                ttime = record["reserve_time"]
                t_hour = int(ttime[0] + ttime[1])
                t_minute = int(ttime[3] + ttime[4])

                q = (t_minute + 1) // 60
                t_minute = (t_minute + time_passed_from_reservation) % 60
                t_hour = t_hour + q

                if current_hour > t_hour or current_minute > t_minute:
                    r.set(key[0] + "_rem", min(ticket_count, int(r.get(key[0] + "_rem")) + 1))
                    r.delete(key)


scheduler = BackgroundScheduler()
time_passed_from_reservation = 1
scheduler.add_job(func=clean_invalid_reservations, trigger="interval", seconds=90)
scheduler.start()


class index_handler(Resource):
    def get(self):
        return make_response(render_template("index.html"
                                             , A_rem=int(r.get("A_rem"))
                                             , B_rem=int(r.get("B_rem"))
                                             , C_rem=int(r.get("C_rem"))
                                             , D_rem=int(r.get("D_rem"))))


class post_redirect_get_index(Resource):
    def post(self):
        params = post_parser.parse_args()
        selected_class = params["selected_class"]

        seat_no = session["seat_no"]

        key = selected_class + str(seat_no)
        if r.exists(key):
            r.delete(key)

        r.set(selected_class + "_rem", min(ticket_count, int(r.get(selected_class + "_rem")) + 1))

        return redirect(url_for("index_handler"))


class post_redirect_get_payment(Resource):
    def post(self):
        params = post_parser.parse_args()
        selected_class = params["selected_class"]

        username = params["username"]

        seat_no = get_last_seat(selected_class)
        # all tickets are sold out
        if seat_no == -1:
            session[selected_class + "_done"] = 1
            return redirect(url_for("payment_show_handler"))

        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")

        # username , seat_no, reserve_time, finalized
        record = {"username": username,
                  "seat_no": seat_no,
                  "reserve_time": current_time,
                  "finalized": 0}
        record = json.dumps(record)
        print()
        print(record)
        print()
        r.set(selected_class + str(seat_no), record)

        r.set(selected_class + "_rem", int(r.get(selected_class + "_rem")) - 1)
        session["selected_class"] = selected_class
        session["seat_no"] = seat_no

        return redirect(url_for("payment_show_handler"))


class payment_show_handler(Resource):
    def get(self):
        selected_class = session["selected_class"]
        return make_response(render_template("payment.html", selected_class=selected_class))


class payment_successful_handler(Resource):
    def post(self):
        params = post_parser.parse_args()
        selected_class = params["selected_class"]

        p = selected_class + "_done"
        if p not in session:
            info = "You bought a ticket from class " + selected_class

            seat_no = session["seat_no"]

            key = selected_class + str(seat_no)
            record = r.get(key)
            record = json.loads(record)
            record["finalized"] = 1
            record = json.dumps(record)

            print()
            print(record)
            print()

            r.set(key, record)

        else:
            info = "Sorry! all tickets in class " + selected_class + " are sold."

        return make_response(render_template("paymentdone.html", info=info
                                             , A_rem=int(r.get("A_rem"))
                                             , B_rem=int(r.get("B_rem"))
                                             , C_rem=int(r.get("C_rem"))
                                             , D_rem=int(r.get("D_rem"))))


api.add_resource(index_handler, "/")
api.add_resource(post_redirect_get_index, "/indexprg")
api.add_resource(post_redirect_get_payment, "/paymentprg")
api.add_resource(payment_show_handler, "/payment")
api.add_resource(payment_successful_handler, "/paymentdone")

if __name__ == "__main__":
    key_num = randrange(10000)
    app.secret_key = "stadium" + str(key_num)
    app.run(host="0.0.0.0", debug=False)
    session.clear()
