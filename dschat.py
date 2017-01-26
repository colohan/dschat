import cgi
import datetime
import jinja2
import json
import os
import pickle
import redis
import urllib
import uwsgi
import webapp2

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)

# If your application is not hosted on the root of your domain, apply this
# prefix before all URLs:
ROUTE_PREFIX = '/dschat'

DEFAULT_NAME = 'Anon E. Mouse'
DEFAULT_EMAIL = 'not@authenticated.com'
DEFAULT_TOPIC = 'chat'

REDIS_CHANNEL = 'messages'
REDIS_ID_KEY = 'id'
REDIS_MESSAGES_KEY = 'messages'


class Message():
    """A main model for representing an individual sent Message."""
    id = 0
    name = DEFAULT_NAME
    email = DEFAULT_EMAIL
    # Note that the date is the only indexed property.  This is because this
    # table is only used for displaying the stream of messages, all searches are
    # done using the Search API:
    date = datetime.MINYEAR
    topic = DEFAULT_TOPIC
    content = ""


def encode_messages(messages):
    """Transforms a list of Messages into escaped JSON for passing to HTML."""

    messages_to_encode = []
    for message in messages:
        messages_to_encode.append({
            'id': cgi.escape(str(message.id).zfill(10)),
            'name': cgi.escape(message.name),
            'email': cgi.escape(message.email),
            'date': cgi.escape(message.date.strftime('%x %X')),
            'topic': cgi.escape(message.topic),
            'content': cgi.escape(message.content).replace("\n", "<br>")
        })
    return json.dumps(messages_to_encode)


class MainPage(webapp2.RequestHandler):
    """Generates the main web page."""

    def get(self):
        topic = self.request.get('topic', DEFAULT_TOPIC)
        user = ''
        token = 0
        template_values = {
            'name': DEFAULT_NAME,
            'email': DEFAULT_EMAIL,
            'topic': urllib.quote_plus(topic),
            'route_prefix': ROUTE_PREFIX
        }

        template = JINJA_ENVIRONMENT.get_template('index.html')
        self.response.write(template.render(template_values))


class SendMessage(webapp2.RequestHandler):
    """Handler for the /send POST request."""

    def post(self):
        # Create a Message and store it in the DataStore.
        #
        # We set the same parent key on the 'Message' to ensure each Message is
        # in the same entity group. Queries across the single entity group will
        # be consistent. However, the write rate to a single entity group should
        # be limited to ~1/second.
        message = Message()

        topic = self.request.get('topic', DEFAULT_TOPIC)
        message.topic = topic
        message.name = self.request.get('name', DEFAULT_NAME)
        message.email = self.request.get('email', DEFAULT_EMAIL)
        message.content = self.request.get('content')
        message.date = datetime.datetime.now()

        r = redis.StrictRedis(host='localhost', port=6379, db=0)

        # Note: ideally we'd do the increment and rpush under the protection of
        # a transaction.  If our program stops (crashes, dies, whatever) between
        # these two lines or if the rpush fails then the database will be left
        # in an inconsistent state and need to be manually corrected so the
        # highest message id == the total # of messages.
        message.id = r.incr(REDIS_ID_KEY)
        r.rpush(REDIS_MESSAGES_KEY, pickle.dumps(message))

        # Now that we've recorded the message in Redis, broadcast it to all open
        # clients.
        r.publish(REDIS_CHANNEL, encode_messages([message]))


def handle_request(r, msg):
    request = json.loads(msg)
    first = int(request["first_id"])
    last = int(request["last_id"])
    # Don't fetch too many messages at once:
    if (last > 0 and (last - 50 > first)) or (last < 0):
        first = last - 50
    pickled_messages = r.lrange(REDIS_MESSAGES_KEY, first, last)
    messages = []
    for pickled_message in pickled_messages:
        message = pickle.loads(pickled_message)
        messages.append(message)

    uwsgi.websocket_send(encode_messages(messages))


class WebSocketConnection(webapp2.RequestHandler):
    """Handles all inbound websocket requests."""

    def get(self):
        # The first thing we need to do is take what seems like a normal HTTP
        # request and upgrade it to be a websocket request:
        uwsgi.websocket_handshake(os.getenv('HTTP_SEC_WEBSOCKET_KEY', ''),
                                  os.getenv('HTTP_ORIGIN', ''))

        # Open a connection to the Redis server, and ask to be notified of any
        # messages on the channel REDIS_CHANNEL:
        r = redis.StrictRedis(host='localhost', port=6379, db=0)
        channel = r.pubsub()
        channel.subscribe(REDIS_CHANNEL)

        # We then want to go to sleep and wait for messages either from Redis,
        # or from this websocket.  So we need to know their file descriptors:
        websocket_fd = uwsgi.connection_fd()
        redis_fd = channel.connection._sock.fileno()

        while True:
            # Setup both FDs with epoll so we can wait for messages.  Wake up
            # every 3 seconds to ensure that ping messages get exchanged on the
            # websocket connection to keep it alive:
            uwsgi.wait_fd_read(websocket_fd, 3)
            uwsgi.wait_fd_read(redis_fd)

            # Put thread to sleep until message arrives or timeout.  Note that
            # if you do not use a suspend engine (such as ugreen) this will just
            # immediately return without suspending, nothing will work, and you
            # will get horribly confused.
            uwsgi.suspend()

            fd = uwsgi.ready_fd()
            if fd > -1:
                if fd == websocket_fd:
                    try:
                        msg = uwsgi.websocket_recv_nb()
                        if msg:
                            handle_request(r, msg)

                    except IOError, e:
                        # Websocket has failed in some way (such as a browser
                        # reload), just close it and let the app re-open if it
                        # is still there to do so:
                        return
                elif fd == redis_fd:
                    # Got a message from Redis, pass it on to the browser
                    # through the websocket.
                    msg = channel.parse_response()
                    # Redis sends both control messages and user messages
                    # through this fd.  Send only user-generated messages to all
                    # clients:
                    if msg[0] == b'message':
                        uwsgi.websocket_send(msg[2])
            else:
                # We got a timeout.  Call websocket_recv_nb again to manage
                # ping/pong:
                try:
                    msg = uwsgi.websocket_recv_nb()
                    if msg:
                        handle_request(r, msg)

                except IOError, e:
                    # Websocket has failed in some way (such as a browser
                    # reload), just close it and let the app re-open if it is
                    # still there to do so:
                    return


real_app = webapp2.WSGIApplication([
    (ROUTE_PREFIX, MainPage),
    (ROUTE_PREFIX + '/', MainPage),
    (ROUTE_PREFIX + '/send', SendMessage),
    (ROUTE_PREFIX + '/get', GetMessages),
    (ROUTE_PREFIX + '/search', SearchPage),
    (ROUTE_PREFIX + '/websocket', WebSocketConnection),
], debug=True)


def fake_start_response(unused1, unused2):
    pass

# When a client disconnects from websocket (say, via a page reload in the
# browser) both the webapp2 framework and the uwsgi websocket framework ends up
# calling start_response.  This generates an annoying exception.  So we provide
# a fake start_response to webapp2 for websocket connections only.  (What a
# gross hack, feel free to tell me a better way...)


def app(environ, start_response):
    if environ['PATH_INFO'] == ROUTE_PREFIX + '/websocket':
        return real_app(environ, fake_start_response)
    return real_app(environ, start_response)
