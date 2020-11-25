// Allow a form to post without navigating to another page:
postForm = function(oFormElement) {
    if (!oFormElement.action) { return; }
    var oReq = new XMLHttpRequest();
    if (oFormElement.method.toLowerCase() === "post") {
        oReq.open("post", oFormElement.action);
        oReq.send(new FormData(oFormElement));
    } else {
        console.error("Can only use post with this!");
    }
}

// Make it so ctrl-Enter can send a message:
onKeyDown = function(e) {
    var keynum;
    var keychar;
    var numcheck;
    keynum = e.keyCode;

    if (e.ctrlKey && (keynum == 13 || // ctrl-Enter
                      keynum == 77)) // ctrl-M (ctrl-Enter on mac firefox does
                                     // this)
    {
        postForm(document.forms["messageForm"]);
        document.getElementById('content').value='';
        return false;
    }
    return true;
}

// Called every time a new message shows up from the server:
onMessage = function(m) {
    // Parse the message received from the server:
    var messages = JSON.parse(m.data);

    var posted_at_bottom = false;
    var height_before = document.body.clientHeight;
    for (var i = 0; i < messages.length; i++) {
        var message = messages[i];

        var newDiv = document.createElement("div");
        newDiv.setAttribute("class", "message");
        newDiv.setAttribute("data-messageid", message.id);
        var newB = document.createElement("b");
        newB.setAttribute("title", message.email);
        newB.textContent = message.name + " (" + message.topic + ") [" + message.date + "]";
        var newBlockquote = document.createElement("blockquote");
        newBlockquote.textContent = message.content;
        newDiv.appendChild(newB);
        newDiv.appendChild(newBlockquote);

        // Now we need to figure out where to add this message.

        var document_messages = document.getElementsByClassName("message");
        var document_messages_length = document_messages.length|0;

        // Optimize for the common cases of it being inserted first or last:
        if (document_messages_length == 0 ||
            parseInt(document_messages[document_messages.length-1].attributes["data-messageid"].value) <
            message.id) {
            var bottom = document.getElementsByClassName("bottom")[0];
            document.body.insertBefore(newDiv, bottom);
            posted_at_bottom = true;

        } else {
            for (var j = 0; j < document_messages_length; j = j+1|0) {
                if (document_messages[j].attributes["data-messageid"].value == message.id) {
                    // Discard duplicate message:
                    break;

                } else if (document_messages[j].attributes["data-messageid"].value > message.id) {
                    document.body.insertBefore(newDiv, document_messages[j]);
                    break;
                }
            }
        }
    }
    var height_after = document.body.clientHeight;

    // Lame attempt at making the window not scroll as we insert new messages at
    // the top.  This doesn't always work very well, feel free to improve this
    // if you are reading this.  :-)
    var new_scroll_position = height_after - height_before;
    if (new_scroll_position > 0 && !posted_at_bottom) {
        window.scroll(0, new_scroll_position);
    }

}

onOpen = function() {
    console.log("Channel to server opened.");

    var document_messages = document.getElementsByClassName("message");
    var document_messages_length = document_messages.length|0;
    if(document_messages_length == 0) {
        fetchMoreMessages();
    }
}

onError = function(e) {
    console.log("Error taking to server: " + e.description + " [code: " +
                e.code + "].");
}

onClose = function() {
    console.log("Channel to server closed");

    // Just sleep 5s and retry:
    setTimeout(openChannel, 5000);
}

var websocket;

// Initialization, called once upon page load:
openChannel = function() {
    var loc = window.location, new_uri;
    if (loc.protocol === "https:") {
        new_uri = "wss:";
    } else {
        new_uri = "ws:";
    }
    new_uri += "//" + loc.host;
    new_uri += loc.pathname + "/websocket";
    websocket = new WebSocket(new_uri);
    websocket.onopen = onOpen;
    websocket.onmessage = onMessage;
    websocket.onerror = onError;
    websocket.onclose = onClose;
}

fetchMoreMessages = function() {
    var document_messages = document.getElementsByClassName("message");
    var document_messages_length = document_messages.length|0;
    var last_id = -1;
    if(document_messages_length > 0) {
        last_id = parseInt(document_messages[0].attributes["data-messageid"].value);
    }

    var request = {
        first_id: 0,  // Ask for as many messages as we can get
        last_id: last_id
    }

    websocket.send(JSON.stringify(request));
}

window.addEventListener('scroll', function() {
    // If the user scrolls up to the top of the window, load some older
    // messages to display for them and insert them into the top.
    if (window.scrollY == 0){
        fetchMoreMessages();
    }
})
;
window.addEventListener('DOMContentLoaded', function() {
    // Scroll to bottom of document
    window.scrollTo(0, document.body.scrollHeight);

    // Open channel back to server to get new messages:
    openChannel();
}, false);
