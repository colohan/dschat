"""Records all messages in a searchable form, and searches them."""

from google.appengine.api import search


index = search.Index(name='Messages')

def add(doc_id, message):
    index.put(search.
              Document(doc_id=doc_id,
                       fields=
                       [search.TextField(name='author',
                                         value=message.author.nickname),
                        search.TextField(name='email',
                                         value=message.author.email),
                        search.TextField(name='topic',
                                         value=message.topic),
                        search.TextField(name='content',
                                         value=message.content),
                        search.DateField(name='date', value=message.date)]))

def find(query, count=10):
    sort_opts = search.SortOptions(expressions=[search.SortExpression(
        expression="date", direction=search.SortExpression.ASCENDING)])
    query_options = search.QueryOptions(limit=count, sort_options=sort_opts)
    query_obj = search.Query(query_string=query, options=query_options)
    results = index.search(query=query_obj)
    keys = []
    for result in results:
        keys.append(result.doc_id)
    return keys
