function Manager(queued_navigator, read_navigator) {
    this.queued_nav = queued_navigator;
    this.read_nav = read_navigator;
    this.cur_nav = queued_navigator;
    this.queued_nav.init();

    var obj = this;
    document.body.onkeypress = function(event) {
        obj.key_press(event)
    }
}

Manager.prototype.key_press = function(event) {
    console.log(event);
    if (event.key == "k") {
        this.cur_nav.up();
    } else if (event.key == "j") {
        this.cur_nav.down();
    } else if (event.key == "f") {
        this.cur_nav.open();
    } else if (event.key == "x") {
        this.cur_nav.delete();
    } else if (event.key == "e") {
        this.cur_nav.edit();
    } else if (event.key == "Enter") {
        this.cur_nav.read();
    } else if (event.key == "q") {
        this.focus_queued();
    } else if(event.key == "r") {
        this.focus_read();
    } else if(event.key == "n") {
        this.toggle_focus();
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

function TableNavigator(table, index) {
    this.table = table;
    this.tbody = table.getElementsByTagName("tbody")[0];
    this.index = index;
}

TableNavigator.prototype.init = function() {
    this.mark(this.index, true);
}

TableNavigator.prototype.mark = function(index, focus) { 
    var row = this.tbody.children[index];
    if (focus) {
        row.classList.add("highlighted-row");
    } else {
        row.classList.remove("highlighted-row");
    }
}

TableNavigator.prototype.set_focus = function(focus) { 
    this.mark(this.index, focus)
}

TableNavigator.prototype.up = function() { 
    // Start at 1 because of the header row
    if (this.index > 1) {
        this.mark(this.index, false)
        this.index -= 1;
        this.mark(this.index, true)
    }
}
TableNavigator.prototype.down = function() { 
    if (this.index < this.tbody.children.length - 1) {
        this.mark(this.index, false)
        this.index += 1;
        this.mark(this.index, true)
    }
}

TableNavigator.prototype.click_button = function(class_name) {
    var row = this.tbody.children[this.index];
    var buttons = row.getElementsByClassName(class_name);
    console.log(buttons);
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
