function Manager(queued_navigator, read_navigator) {
    this.queued_nav = queued_navigator;
    this.read_nav = read_navigator;
    this.cur_nav = queued_navigator;

    // Initialize TableNavigators
    var obj = this;
    this.queued_nav.init(this, function() { obj.focus_queued(); });
    this.read_nav.init(this, function() { obj.focus_read(); });
    this.queued_nav.mark(this.queued_nav.index, true);

    // Set up key events
    document.body.onkeydown = function(event) {
        obj.key_down(event);
    }
    document.body.onkeyup = function(event) {
        obj.key_up(event);
    }
}

Manager.prototype.key_down = function(event) {
    console.log(event);
    if (event.key == "Escape") {
        document.activeElement.blur();
    } else if (document.activeElement !== document.getElementById("linkbar")
               && !event.ctrlKey && !event.altKey && !event.metaKey) {
        // Only do these if the linkbar is not in focus and ctrl/alt/cmd are not pressed
        if (event.key == "k" || event.key == "ArrowUp") {
            this.cur_nav.up(1);
        } else if (event.key == "j" || event.key == "ArrowDown") {
            this.cur_nav.down(1);
        } else if (event.key == "u") {
            this.cur_nav.up(5);
        } else if (event.key == "d") {
            this.cur_nav.down(5);
        } else if (event.key == "g") {
            this.cur_nav.move_to_top();
        } else if (event.key == "G") {
            this.cur_nav.move_to_bottom();
        } else if (event.key == "e") {
            this.cur_nav.open();
        } else if (event.key == "x") {
            this.cur_nav.delete();
        } else if (event.key == "s") {
            this.cur_nav.edit();
        } else if (event.key == "f") {
            this.cur_nav.read();
        } else if (event.key == "q") {
            this.focus_queued();
        } else if(event.key == "r") {
            this.focus_read();
        } else if(event.key == "n") {
            this.toggle_focus();
        } else if(event.key == "?") {
            this.toggle_shortcuts_modal();
        }
    }
}

Manager.prototype.key_up = function(event) {
    if(event.key == "i") {
        document.getElementById("linkbar").focus();
    }
}

Manager.prototype.focus_queued = function() {
    this.queued_nav.set_focus(true);
    this.read_nav.set_focus(false);
    this.cur_nav = this.queued_nav;
}

Manager.prototype.focus_read = function() {
    this.queued_nav.set_focus(false);
    this.read_nav.set_focus(true);
    this.cur_nav = this.read_nav;
}

Manager.prototype.toggle_focus = function() {
    if (this.cur_nav === this.queued_nav) {
        this.focus_read();
    } else {
        this.focus_queued();
    }
}

Manager.prototype.toggle_shortcuts_modal = function() {
    var button = document.getElementById('modalShortcutsButton');
    button.click();
}

function TableNavigator(table, index) {
    this.table = table;
    this.tbody = table.getElementsByTagName("tbody")[0];
    this.index = index;
}

TableNavigator.prototype.init = function(manager, focus_func) {
    var obj = this;
    function create_onclick(i) {
        return function() {
            obj.focus_and_mark(i);
            focus_func();
        }
    }
    for (var i = 1; i < this.tbody.children.length; i++) {
        this.tbody.children[i].onclick = create_onclick(i);
    }
}

TableNavigator.prototype.mark = function(index, focus) { 
    var row = this.tbody.children[index];
    document.querySelector('html').classList.add('scroll-auto');
    if (focus) {
        row.classList.add("highlighted-row");
        var rect = row.getBoundingClientRect();
        console.log(rect)
        if (rect.bottom > window.innerHeight) {
            // Scroll down
            window.scrollTo(window.scrollX, window.scrollY + rect.bottom - window.innerHeight + 5);
        } else if (rect.top < 0 || window.scrollY + rect.top < 200) {
            if (window.scrollY + rect.top < 200) {
                // Just scroll to top of page
                window.scrollTo(window.scrollX, 0);
            } else if (index == 1) {
                // Scroll to the top of the table
                window.scrollTo(window.scrollX, window.scrollY + this.tbody.children[0].getBoundingClientRect().top - 55)
            } else {
                // Scroll up
                window.scrollTo(window.scrollX, window.scrollY + rect.top - 55);
            }
        }
    } else {
        row.classList.remove("highlighted-row");
    }
    document.querySelector('html').classList.remove('scroll-auto');
}

TableNavigator.prototype.set_focus = function(focus) { 
    this.mark(this.index, focus)
}

TableNavigator.prototype.focus_and_mark = function(index) {
    this.mark(this.index, false)
    this.index = index;
    this.mark(this.index, true)
}

TableNavigator.prototype.focus_and_mark_by_paper_id = function(paper_id) {
    for (var i = 1; i < this.tbody.children.length; i++) {
        var row = this.tbody.children[i];
        if (row.dataset.paperid == paper_id) {
            this.focus_and_mark(i);
            return;
        }
    }
}

TableNavigator.prototype.up = function(dx) {
    // Start at 1 because of the header row
    var new_index = this.index - dx;
    if (new_index < 1) {
        new_index = 1;
    }
    this.focus_and_mark(new_index);
}
TableNavigator.prototype.down = function(dx) {
    var new_index = this.index + dx;
    if (new_index >= this.tbody.children.length) {
        new_index = this.tbody.children.length - 1
    }
    this.focus_and_mark(new_index);
}
TableNavigator.prototype.move_to_top = function() {
    this.focus_and_mark(1);
}
TableNavigator.prototype.move_to_bottom = function() {
    this.focus_and_mark(this.tbody.children.length - 1);
}

TableNavigator.prototype.click_button = function(class_name) {
    var row = this.tbody.children[this.index];
    var buttons = row.getElementsByClassName(class_name);
    if (buttons.length > 0) {
        buttons[0].click()
    }
}

TableNavigator.prototype.open = function() {
    this.click_button("link-title");
}
TableNavigator.prototype.delete = function() { 
    this.click_button("delete-button");
}
TableNavigator.prototype.edit = function() { 
    this.click_button("edit-button");
}
TableNavigator.prototype.read = function() { 
    this.click_button("read-button");
}
