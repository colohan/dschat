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
    var height_before = $(document).height();
    for (var i = 0; i < messages.length; i++) {
	var message = messages[i];
	
	var html = "<div class=\"message\" data-messageid=\"" + message.id +
	    "\"><b title=\"" + message.email + "\">" + message.nickname + " (" +
            message.topic + ") [" + message.date + "]</b><blockquote>" +
            message.content + "</blockquote></div>";

	// Now we need to figure out where to add this message.  Optimize for
	// the common cases of it being inserted first or last:
	if ($(".message").last().attr("data-messageid") < message.id) {
	    $(".message").last().after(html);
	    posted_at_bottom = true;

	} else {
	    var iter = $(".message").first();
	    while (iter != null) {
		if (iter.attr("data-messageid") == message.id) {
		    // Discard duplicate message:
		    iter = null;

		} else if (iter.attr("data-messageid") > message.id) {
		    iter.before(html);
		    iter = null;

		} else {
		    iter = iter.next();
		}
	    }
	}
    }
    var height_after = $(document).height();
    
    // Lame attempt at making the window not scroll as we insert new messages at
    // the top.  This doesn't always work very well, feel free to improve this
    // if you are reading this.  :-)
    var new_scroll_position = height_after - height_before;
    if (new_scroll_position > 0 && !posted_at_bottom) {
	$(window).scrollTop(new_scroll_position);
    }
    
}

onOpen = function() {
    console.log("Channel to server opened.");
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

// Initialization, called once upon page load:
openChannel = function() {
    var channel = new goog.appengine.Channel(token);
    var handler = {
        'onopen': onOpen,
        'onmessage': onMessage,
        'onerror': onError,
        'onclose': onClose
    };
    var socket = channel.open(handler);
}

fetchMoreMessages = function() {
    // Send a "get" request back to the server so it provides us with messages
    // older than last_id:
    var last_id = $(".message").first().attr("data-messageid")
    $.post("get", {older_than: last_id});
}

onScroll = function() {
    // If the user scrolls up to the top of the window, load some older
    // messages to display for them and insert them into the top.
    if ($(window).scrollTop() == 0){
	fetchMoreMessages();
    }
}

// Invoked by jQuery once the DOM is constructed:
$(function () {
    // Set callback to invoke when window scrolls:
    $(window).on("scroll", onScroll);

    // Scroll to bottom of document
    $(window).scrollTop($(document).height() - $(window).height());
    
    // Open channel back to server to get new messages:
    openChannel();
});
