# dschat

AppEngine version of the dschat online chat system.  Inspired by the zarchive
interface to the Zephyr chat system used by CS grad students at Carnegie Mellon.

This is a example program.  It is not guaranteed to be complete, robust, or
anything else.  Note that if you deploy this to AppEngine and get a lot of
active users (or one runaway bot), it may cost you money to run this.  Be
careful!

Note that I am far from an expert in Python, and this is the first Javascript
program I ever wrote.  I'm a C++ guy.  Don't use my code as an example of "good
practice", as it probably isn't.

===

If you change this app and want to test it on your local computer, use:

  dev_appserver.py .

To deploy the new version to AppEngine, use:

  gcloud app deploy app.yaml

If you make a change which issues new datastore queries, run the following to
cause AppEngine to build new indexes:

  gcloud app deploy index.yaml

