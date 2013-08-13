#
# Copyright 2009-2012 Alex Fraser <alex@phatcore.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import weakref
import logging

#
# Containers
#

def weakprop(name):
    '''Creates a property that stores a weak reference to whatever is assigned
    to it. If the assignee is deleted, the getter will return None. Example
    usage:

    class Baz:
        foo = bat.containers.weakprop('foo')

        def bork(self, gameObject):
            self.foo = gameObject

        def update(self):
            if self.foo != None:
                self.foo.worldPosition.z += 1
    '''
    hiddenName = '_wp_' + name

    def createweakprop(hiddenName):
        def wp_getter(slf):
            ref = None
            try:
                ref = getattr(slf, hiddenName)
            except AttributeError:
                pass

            value = None
            if ref != None:
                value = ref()
                if value is None:
                    setattr(slf, hiddenName, None)
                elif hasattr(value, 'invalid') and value.invalid:
                    setattr(slf, hiddenName, None)
                    value = None
            return value

        def wp_setter(slf, value):
            if value is None:
                setattr(slf, hiddenName, None)
            else:
                ref = weakref.ref(value)
                setattr(slf, hiddenName, ref)

        return property(wp_getter, wp_setter)

    return createweakprop(hiddenName)


class SafeList:
    '''
    A list that only stores references to valid objects. An object that has the
    'invalid' attribute will be ignored if ob.invalid is False. This has
    implications for the indices of the list: indices may change from one frame
    to the next, but they should remain consistent during a frame.
    '''

    def __init__(self, iterable = None):
        self._list = []
        if iterable is not None:
            self.extend(iterable)

    def __contains__(self, item):
        if hasattr(item, 'invalid') and item.invalid:
            return False
        return self._list.__contains__(item)

    def __iter__(self):
        def _iterator():
            i = self._list.__iter__()
            while True:
                item = next(i)
                if hasattr(item, 'invalid') and item.invalid:
                    continue
                yield item
        return _iterator()

    def __len__(self):
        n = 0
        for item in self._list:
            if hasattr(item, 'invalid') and item.invalid:
                continue
            n += 1
        return n

    def append(self, item):
        self._expunge()
        if hasattr(item, 'invalid') and item.invalid:
            return
        return self._list.append(item)

    def index(self, item):
        i = 0
        for item2 in self._list:
            if hasattr(item2, 'invalid') and item2.invalid:
                continue
            if item2 is item:
                return i
            else:
                i += 1
        raise ValueError("Item is not in list")

    def remove(self, item):
        self._expunge()
        if hasattr(item, 'invalid') and item.invalid:
            raise ValueError("Item has expired.")
        return self._list.remove(item)

    def pop(self, index=-1):
        self._expunge()
        return self._list.pop(index)

    def extend(self, iterable):
        for item in iterable:
            self.append(item)

    def count(self, item):
        if hasattr(item, 'invalid') and item.invalid:
            return 0
        return self._list.count(item)

    def __getitem__(self, index):
        # Todo: allow negative indices.
        if index < 0:
            i = -1
            for item in reversed(self._list):
                if hasattr(item, 'invalid') and item.invalid:
                    continue
                if i == index:
                    return item
                else:
                    i -= 1
        else:
            i = 0
            for item in self._list:
                if hasattr(item, 'invalid') and item.invalid:
                    continue
                if i == index:
                    return item
                else:
                    i += 1
        raise IndexError("list index out of range")

    def __setitem__(self, index, item):
        self._expunge()
        # After expunging, the all items in the internal list will have the
        # right length - so it's OK to just call the wrapped method.
        if hasattr(item, 'invalid') and item.invalid:
            return item
        return self._list.__setitem__(index, item)

    def __delitem__(self, index):
        self._expunge()
        return self._list.__delitem__(index)

    def insert(self, index, item):
        self._expunge()
        if hasattr(item, 'invalid') and item.invalid:
            return
        self._list.insert(index, item)

    def _expunge(self):
        new_list = []
        for item in self._list:
            if hasattr(item, 'invalid') and item.invalid:
                self._on_automatic_removal(item)
            else:
                new_list.append(item)
        self._list = new_list

    def __str__(self):
        return str(list(self))

    def _on_automatic_removal(self, item):
        pass


class SafeSet:
    '''A set for PyObjectPlus objects. This container ensures that its contents
    are valid (living) game objects.

    As usual, you shouldn't change the contents of the set while iterating over
    it. However, an object dying in the scene won't invalidate existing
    iterators.'''

    def __init__(self, iterable = None):
        self.bag = set()
        self.deadBag = set()
        if iterable != None:
            for ob in iterable:
                self.add(ob)

    def copy(self):
        clone = SafeSet()
        clone.bag = self.bag.copy()
        clone.deadBag = self.deadBag.copy()
        clone._expunge()
        return clone

    def __contains__(self, item):
        if hasattr(item, 'invalid') and item.invalid:
            if item in self.bag:
                self._flag_removal(item)
            return False
        else:
            return item in self.bag

    def __iter__(self):
        for item in self.bag:
            if hasattr(item, 'invalid') and item.invalid:
                self._flag_removal(item)
            else:
                yield item

    def __len__(self):
        # Unfortunately the only way to be sure is to check each object!
        count = 0
        for item in self.bag:
            if hasattr(item, 'invalid') and item.invalid:
                self._flag_removal(item)
            else:
                count += 1
        return count

    def add(self, item):
        self._expunge()
        if hasattr(item, 'invalid') and item.invalid:
            return
        self.bag.add(item)

    def discard(self, item):
        self.bag.discard(item)
        self._expunge()

    def remove(self, item):
        self.bag.remove(item)
        self._expunge()

    def update(self, iterable):
        self.bag.update(iterable)
        self._expunge()

    def union(self, iterable):
        newset = SafeSet()
        newset.bag = self.bag.union(iterable)
        return newset

    def difference_update(self, iterable):
        self.bag.difference_update(iterable)
        self._expunge()

    def difference(self, iterable):
        newset = SafeSet()
        newset.bag = self.bag.difference(iterable)
        return newset

    def intersection_update(self, iterable):
        self.bag.intersection_update(iterable)
        self._expunge()

    def intersection(self, iterable):
        newset = SafeSet()
        newset.bag = self.bag.intersection(iterable)
        return newset

    def clear(self):
        self.bag.clear()
        self.deadBag.clear()

    def _flag_removal(self, item):
        '''Mark an object for garbage collection. Actual removal happens at the
        next explicit mutation (add() or discard()).'''
        self.deadBag.add(item)

    def _expunge(self):
        '''Remove objects marked as being dead.'''
        self.bag.difference_update(self.deadBag)
        self.deadBag.clear()

    def __str__(self):
        return str(self.bag)

class SafePriorityStack(SafeList):
    '''
    A poor man's associative priority queue. This is likely to be slow. It is
    only meant to contain a small number of items.
    '''

    log = logging.getLogger(__name__ + '.SafePriorityStack')

    def __init__(self):
        '''Create a new, empty priority queue.'''
        super(SafePriorityStack, self).__init__()
        self.priorities = {}

    def push(self, item, priority):
        '''Add an item to the stack. If the item is already in the stack, it is
        removed and added again using the new priority.

        Parameters:
        item:     The item to place on the stack.
        priority: Items with higher priority will be stored higher on the stack.
                  0 <= priority. (Integer)
        '''

        SafePriorityStack.log.debug("push %s@%s", item, priority)

        if item in self.priorities:
            self.discard(item)

        # Insert at the front of the list of like-priority items.
        idx = 0
        for other in self:
            if self.priorities[other] <= priority:
                break
            idx += 1
        super(SafePriorityStack, self).insert(idx, item)

        self.priorities[item] = priority

    def _on_automatic_removal(self, item):
        SafePriorityStack.log.debug("Auto remove %s", item)
        del self.priorities[item]

    def discard(self, item):
        '''Remove an item from the queue.

        Parameters:
        key: The key that was used to insert the item.
        '''
        SafePriorityStack.log.debug("Discard %s", item)
        try:
            super(SafePriorityStack, self).remove(item)
            del self.priorities[item]
        except KeyError:
            pass
        except ValueError:
            pass

    def pop(self):
        '''Remove the highest item in the queue.

        Returns: the item that is being removed.

        Raises:
        IndexError: if the queue is empty.
        '''

        SafePriorityStack.log.debug("pop")
        item = super(SafePriorityStack, self).pop(0)
        del self.priorities[item]
        return item

    def top(self):
        return self[0]

    def append(self, item):
        raise NotImplementedError("Use 'push' instead.")

    def remove(self, item):
        raise NotImplementedError("Use 'discard' instead.")

    def __setitem__(self, index, item):
        raise NotImplementedError("Use 'push' instead.")

    def insert(self, index, item):
        raise NotImplementedError("Use 'push' instead.")

    def __str__(self):
        string = "["
        for item in self:
            if len(string) > 1:
                string += ", "
            string += "%s@%d" % (item, self.priorities[item])
        string += "]"
        return string
