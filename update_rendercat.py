#!/usr/bin/env python3
"""Replace renderCategoryManager function - simpler approach."""
p = '/Users/ZAHER/Desktop/مذكرتي_الذكية_PWA/static/index.html'
with open(p, 'r') as f:
    c = f.read()

# Find the entire old function
marker_start = 'function renderCategoryManager(){'
old_start = c.find(marker_start)
if old_start < 0:
    print('FAIL: function not found')
    exit(1)

# Find the end: it's the last ')}' that closes the function 
# The function ends with ...لا توجد أنواع روابط مخصصة.</p>')}
marker_end = "لا توجد أنواع روابط مخصصة.</p>')}"
old_end = c.find(marker_end, old_start)
if old_end < 0:
    print('FAIL: end marker not found')
    exit(1)
old_end += len(marker_end)  # include the closing sequence

old_func = c[old_start:old_end]
print(f'Found function at index {old_start}-{old_end}')

# Build new function
# Constants for the delete buttons (repeated pattern)
btn_style = 'style="display:flex;justify-content:space-between;align-items:center;border:1px solid var(--line);border-radius:16px;padding:10px;margin:6px 0"'

new_func = (
    'function renderCategoryManager(){'
    'let cats=getCustomCategories(),types=getCustomLinkTypes(),'
    'ntypes=getCustomNoteTypes(),moods=getCustomMoods();'
    "$('catCount').textContent=cats.length;"
    "$('typeCount').textContent=types.length;"
    "$('noteTypeCount').textContent=ntypes.length;"
    "$('moodCount').textContent=moods.length;"
    
    # cats list
    "$('catsList').innerHTML=(cats.length?"
    "cats.map(c=>'<div "+btn_style+"><b>'+c+'</b>"
    '<button class="smallBtn" '
    "onclick=\"removeCustomCategory('"+c+"');"
    "renderCategoryManager();populatePlaceCategories();"
    "toast('حذف: '+c+')\">✕</button></div>').join(''):"
    "'<p class=\"muted\">لا توجد تصنيفات مخصصة للمواقع.</p>');"
    
    # types list
    "$('typesList').innerHTML=(types.length?"
    "types.map(t=>'<div "+btn_style+"><b>'+t+'</b>"
    '<button class="smallBtn" '
    "onclick=\"removeCustomLinkType('"+t+"');"
    "renderCategoryManager();populateLinkTypes();"
    "toast('حذف: '+t+')\">✕</button></div>").join(''):"
    "'<p class=\"muted\">لا توجد أنواع روابط مخصصة.</p>');"
    
    # note types list
    "$('noteTypesList').innerHTML=(ntypes.length?"
    "ntypes.map(n=>'<div "+btn_style+"><b>'+n+'</b>"
    '<button class="smallBtn" '
    "onclick=\"removeCustomNoteType('"+n+"');"
    "renderCategoryManager();renderNoteChoices();"
    "toast('حذف: '+n+')\">✕</button></div>").join(''):"
    "'<p class=\"muted\">لا توجد أنواع مذكرات مخصصة.</p>');"
    
    # moods list
    "$('moodsList').innerHTML=(moods.length?"
    "moods.map(m=>'<div "+btn_style+"><b>'+m+'</b>"
    '<button class="smallBtn" '
    "onclick=\"removeCustomMood('"+m+"');"
    "renderCategoryManager();renderNoteChoices();"
    "toast('حذف: '+m+')\">✕</button></div>").join(''):"
    "'<p class=\"muted\">لا توجد حالات مخصصة.</p>')}"
)

# Check old function content matches
print(f'Old func length: {len(old_func)}')
print(f'New func length: {len(new_func)}')

c = c[:old_start] + new_func + c[old_end:]

# Verify no original escape patterns left
if '\\\\' in new_func:
    print('WARNING: double backslash found in new function, might be wrong')
    
with open(p, 'w') as f:
    f.write(c)
print('✅ SUCCESS: renderCategoryManager updated')
