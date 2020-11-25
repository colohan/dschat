try:
    from functools import lru_cache
except ImportError:
    from functools32 import lru_cache
import base64
import cgi
import datetime
import httplib2
import jinja2
import json
import messageindex
import os
import re
import time
import urllib
import webapp2


from google.appengine.api import app_identity
from google.appengine.api import users
from google.appengine.ext import ndb
from oauth2client.client import GoogleCredentials


JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)

_IDENTITY_ENDPOINT = ('https://identitytoolkit.googleapis.com/'
                      'google.identity.identitytoolkit.v1.IdentityToolkit')
_FIREBASE_SCOPES = [
    'https://www.googleapis.com/auth/firebase.database',
    'https://www.googleapis.com/auth/userinfo.email']

DEFAULT_TOPIC = 'chat'

def messages_key():
    """Constructs a Datastore key for the Messages table.
    """
    return ndb.Key('Messages', 'Public')


def sessions_key():
    """Constructs a Datastore key for the Sessions table.
    """
    return ndb.Key('Sessions', 'All')


class Author(ndb.Model):
    """Sub model for representing an author."""
    identity = ndb.StringProperty(indexed=False)
    nickname = ndb.StringProperty(indexed=False)
    email = ndb.StringProperty(indexed=False)


class Message(ndb.Model):
    """A main model for representing an individual sent Message."""
    author = ndb.StructuredProperty(Author)
    # Note that the date is the only indexed property.  This is because this
    # table is only used for displaying the stream of messages, all searches are
    # done using the Search API:
    date = ndb.DateTimeProperty()
    topic = ndb.StringProperty(indexed=False)
    content = ndb.StringProperty(indexed=False)


class Session(ndb.Model):
    """A main model for representing an user's session."""
    client_id = ndb.StringProperty(indexed=True)
    # Not used, only for making administration easier:
    email = ndb.StringProperty(indexed=False)


def message_to_struct(message):
    """Transforms a Message into a simple structure for passing to HTML."""

    struct_message = {
        'id': cgi.escape(message.date.isoformat()),
        'nickname': cgi.escape(message.author.nickname),
        'email': cgi.escape(message.author.email),
        'date': cgi.escape(message.date.strftime('%x %X')),
        'topic': cgi.escape(message.topic),
        'content': cgi.escape(message.content).replace("\n", "<br>")
    }
    return struct_message


def create_custom_token(uid, valid_minutes=59):
    """Create a secure token for the given id.

    This method is used to create secure custom JWT tokens to be passed to
    clients. It takes a unique id (user_id) that will be used by Firebase's
    security rules to prevent unauthorized access.
    """

    # use the app_identity service from google.appengine.api to get the
    # project's service account email automatically
    client_email = app_identity.get_service_account_name()

    now = int(time.time())
    # encode the required claims
    # per https://firebase.google.com/docs/auth/server/create-custom-tokens
    payload = base64.b64encode(json.dumps({
        'iss': client_email,
        'sub': client_email,
        'aud': _IDENTITY_ENDPOINT,
        'uid': uid,  # the important parameter, as it will be the channel id
        'iat': now,
        'exp': now + (valid_minutes * 60),
    }))
    # add standard header to identify this as a JWT
    header = base64.b64encode(json.dumps({'typ': 'JWT', 'alg': 'RS256'}))
    to_sign = '{}.{}'.format(header, payload)
    # Sign the jwt using the built in app_identity service
    return '{}.{}'.format(to_sign, base64.b64encode(
        app_identity.sign_blob(to_sign)[1]))


class MainPage(webapp2.RequestHandler):
    """Generates the main web page."""

    def get(self):
        user = users.get_current_user()
        if not user:
            # This should never happen, as AppEngine should only run this
            # handler if the user is signed in.  But defense in depth applies...
            self.redirect(users.create_login_url(self.request.uri))
            return

        # If this user has not used the system before, add their user_id to the
        # table of IDs which we attempt to broadcast all messages to.
        #
        # Room for improvement: right now this table will grow endlessly as more
        # and more people use the system.  This may not scale if the system
        # becomes popular.  We actually only want a list of people with open
        # sessions.
        #
        # Idea: have a heartbeat from clients, and expire entries in this table
        # which have not gotten a heartbeat in a long time.  You might worry
        # that this server could be DoSed by getting too many heartbeats from a
        # large number of simultaneously active clients -- but this system is
        # already broadcasting to all active clients anyways, so we'll hit
        # scaling issues in the broadcast (which we'll have to solve) long
        # before we get DoSed by inbound heartbeats.
        query = Session.query(Session.client_id == user.user_id())
        if query.iter().has_next():
            session = query.iter().next()
        else:
            session = Session(parent=sessions_key())
            session.client_id = user.user_id();
            session.email = user.email();
            session.put()

        topic = self.request.get('topic', DEFAULT_TOPIC)

        # encrypt the channel_id and send it as a custom token to the
        # client
        # Firebase's data security rules will be able to decrypt the
        # token and prevent unauthorized access
        token = create_custom_token(session.client_id)

        template_values = {
            'user': user,
            'topic': urllib.quote_plus(topic),
            'token': token,
            'channel_id': user.user_id(),
        }

        template = JINJA_ENVIRONMENT.get_template('index.html')
        self.response.write(template.render(template_values))


def safeStrToInt(s):
    try:
        return int(s)
    except ValueError:
        return 10


class SearchPage(webapp2.RequestHandler):
    """Generates the search results page."""
    def get(self):
        self.post()

    def post(self):
        user = users.get_current_user()
        if not user:
            # This should never happen, as AppEngine should only run this
            # handler if the user is signed in.  But defense in depth applies...
            self.redirect(users.create_login_url(self.request.uri))
            return

        query = self.request.get('query', '')
        num_results = safeStrToInt(self.request.get('num_results', '10'))

        urlsafe_keys = messageindex.find(query, num_results)


        results = []
        for urlsafe_key in urlsafe_keys:
            result = ndb.Key(urlsafe=urlsafe_key).get()
            if result:
                results.append(message_to_struct(result))

        template_values = {
            'query': query,
            'num_results': num_results,
            'results': results
        }

        template = JINJA_ENVIRONMENT.get_template('search.html')
        self.response.write(template.render(template_values))


# Memoize the value, to avoid parsing the code snippet every time
@lru_cache()
def _get_firebase_db_url():
    """Grabs the databaseURL from the Firebase config snippet. Regex looks
    scary, but all it is doing is pulling the 'databaseURL' field from the
    Firebase javascript snippet"""
    regex = re.compile(r'\bdatabaseURL\b.*?["\']([^"\']+)')
    cwd = os.path.dirname(__file__)
    try:
        with open(os.path.join(cwd, 'index.html')) as f:
            url = next(regex.search(line) for line in f if regex.search(
                line))
    except StopIteration:
        raise ValueError(
            'Error parsing databaseURL. Please copy Firebase web snippet '
            'into index.html')
    return url.group(1)

# Memoize the authorized http, to avoid fetching new access tokens
@lru_cache()
def _get_http():
    """Provides an authed http object."""
    http = httplib2.Http()
    # Use application default credentials to make the Firebase calls
    # https://firebase.google.com/docs/reference/rest/database/user-auth
    creds = GoogleCredentials.get_application_default().create_scoped(
        _FIREBASE_SCOPES)
    creds.authorize(http)
    return http

class MessagesBroadcast():
    """Given an array of messages, broadcast it to all users who have opened the UI."""
    message = None

    def __init__(self, messages):
        self.messages = messages

    def encode_messages(self):
        struct_encoded = []
        for message in self.messages:
            struct_encoded.append(message_to_struct(message))
        return json.dumps(struct_encoded)

    def send_messages(self, dest):
        str_message = self.encode_messages()
        url = '{}/channels/{}.json'.format(_get_firebase_db_url(), dest)
        _get_http().request(url, 'PUT', body=str_message)

    def send(self):
        # Iterate over all logged in users and attempt to forward the message to
        # them:
        session_query = Session.query(ancestor=sessions_key())
        for session in session_query:
            self.send_messages(session.client_id)


class SendMessage(webapp2.RequestHandler):
    """Handler for the /send POST request."""
    def post(self):
        user = users.get_current_user()
        if not user:
            # This should never happen, as AppEngine should only run this
            # handler if the user is signed in.  But defense in depth applies...
            self.redirect(users.create_login_url(self.request.uri))
            return

        # Create a Message and store it in the DataStore.
        #
        # We set the same parent key on the 'Message' to ensure each Message is
        # in the same entity group. Queries across the single entity group will
        # be consistent. However, the write rate to a single entity group should
        # be limited to ~1/second.
        message = Message(parent=messages_key())

        topic = self.request.get('topic', DEFAULT_TOPIC)
        message.topic = topic
        message.author = Author(
                identity=user.user_id(),
                nickname=user.nickname(),
                email=user.email())
        message.content = self.request.get('content')
        message.date = datetime.datetime.now()
        message_key = message.put()

        # Index the message so it is available for future searches:
        messageindex.add(message_key.urlsafe(), message)

        # Now that we've recorded the message in the DataStore, broadcast it to
        # all open clients.
        broadcast = MessagesBroadcast([message])
        broadcast.send()


class GetMessages(webapp2.RequestHandler):
    """Handler for the /get POST request."""
    def post(self):
        user = users.get_current_user()
        if not user:
            # This should never happen, as AppEngine should only run this
            # handler if the user is signed in.  But defense in depth applies...
            self.redirect(users.create_login_url(self.request.uri))
            return

        older_than_id = self.request.get('older_than')
        older_than = datetime.datetime.strptime(older_than_id,
                                                "%Y-%m-%dT%H:%M:%S.%f")

        query = Message.query(ancestor=messages_key()).filter(Message.date <
                                                              older_than
        ).order(-Message.date)
        # Limit query to 50 messages:
        query_results = query.fetch(50)

        if len(query_results) > 0:
            broadcast = MessagesBroadcast(query_results)
            broadcast.send_messages(user.user_id())


app = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/send', SendMessage),
    ('/get', GetMessages),
    ('/search', SearchPage),
], debug=True)
