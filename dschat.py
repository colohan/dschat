import cgi
import datetime
import os
import urllib
import jinja2
import webapp2
import messageindex
import json


from google.appengine.api import channel
from google.appengine.api import users
from google.appengine.ext import ndb


JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)

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
        if not query.iter().has_next():
            session = Session(parent=sessions_key())
            session.client_id = user.user_id();
            session.email = user.email();
            session.put()

        # Just fetch some messages from the past month to populate the UI.  At
        # some point in the future we should make this customizable (perhaps
        # after we add search functionality).
        query = Message.query(ancestor=messages_key()).filter(
            Message.date > (datetime.datetime.now() -
                            datetime.timedelta(days=30))
        ).order(-Message.date)
        # Limit query to 50 messages in case something goes haywire.
        query_results = query.fetch(50)

        messages = []
        for result in reversed(query_results):
            messages.append(message_to_struct(result))

        topic = self.request.get('topic', DEFAULT_TOPIC)
        token = channel.create_channel(user.user_id());
            
        # FIXME: should clone messages array and cgi.escape all elements in it,
        # instead of relying upon JINJA to do this.  In the process, we can
        # replace newlines with <br> (see encode_message below for code).

        template_values = {
            'user': user,
            'messages': messages,
            'topic': urllib.quote_plus(topic),
            'token': token,
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
            results.append(message_to_struct(
                ndb.Key(urlsafe=urlsafe_key).get()))

        template_values = {
            'query': query,
            'num_results': num_results,
            'results': results
        }

        template = JINJA_ENVIRONMENT.get_template('search.html')
        self.response.write(template.render(template_values))


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
        channel.send_message(dest, str_message)

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

        broadcast = MessagesBroadcast(query_results)
        broadcast.send_messages(user.user_id())

            
app = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/send', SendMessage),
    ('/get', GetMessages),
    ('/search', SearchPage),
], debug=True)
