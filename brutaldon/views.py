from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.cache import never_cache
from brutaldon.forms import LoginForm, SettingsForm, PostForm
from brutaldon.models import Client, Account
from mastodon import Mastodon
from urllib import parse
from  django.core.files.uploadhandler import TemporaryFileUploadHandler

class NotLoggedInException(Exception):
    pass

def get_mastodon(request):
    if not (request.session.has_key('instance') and
            request.session.has_key('username')):
        raise NotLoggedInException()

    try:
        client = Client.objects.get(api_base_id=request.session['instance'])
        user = Account.objects.get(username=request.session['username'])
    except (Client.DoesNotExist, Client.MultipleObjectsReturned,
            Account.DoesNotExist, Account.MultipleObjectsReturned):
        raise NotLoggedInException()

    mastodon = Mastodon(
        client_id = client.client_id,
        client_secret = client.client_secret,
        access_token = user.access_token,
        api_base_url = client.api_base_id,
        ratelimit_method="pace")
    return mastodon

def fullbrutalism_p(request):
    if request.session.has_key('fullbrutalism'):
        fullbrutalism = request.session['fullbrutalism']
    else:
        fullbrutalism = False
    return fullbrutalism

def timeline(request, timeline='home', timeline_name='Home'):
    try:
        mastodon = get_mastodon(request)
    except NotLoggedInException:
        return redirect(login)
    data = mastodon.timeline(timeline)
    form = PostForm()
    return render(request, 'main/timeline.html',
                  {'toots': data, 'form': form, 'timeline': timeline_name,
                   'fullbrutalism': fullbrutalism_p(request)})

@never_cache
def home(request):
    return timeline(request, 'home', 'Home')

@never_cache
def local(request):
    return timeline(request, 'local', 'Local')

@never_cache
def fed(request):
    return timeline(request, 'public', 'Federated')

def login(request):
    if request.method == "GET":
        form = LoginForm()
        return render(request, 'setup/login.html', {'form': form})
    elif request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            api_base_url = form.cleaned_data['instance']
            # Fixme, make sure this is url
            tmp_base = parse.urlparse(api_base_url.lower())
            if tmp_base.netloc == '':
                api_base_url = parse.urlunparse(('https', tmp_base.path,
                                                 '','','',''))
            else:
                api_base_url = api_base_url.lower()

            request.session['instance'] = api_base_url
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']

            try:
                client = Client.objects.get(api_base_id=api_base_url)
            except (Client.DoesNotExist, Client.MultipleObjectsReturned):
                (client_id, client_secret) = Mastodon.create_app('brutaldon',
                                                             api_base_url=api_base_url)
                client = Client(
                    api_base_id = api_base_url,
                    client_id=client_id,
                    client_secret = client_secret)
                client.save()

            mastodon = Mastodon(
                client_id = client.client_id,
                client_secret = client.client_secret,
                api_base_url = api_base_url)

            try:
                account = Account.objects.get(username=username, client_id=client.id)
            except (Account.DoesNotExist, Account.MultipleObjectsReturned):
                account = Account(
                    username = username,
                    access_token = "",
                    client = client)
            try:
                access_token = mastodon.log_in(username,
                                               password)
                account.access_token = access_token
                account.save()
                request.session['username'] = username

                return redirect(home)
            except:
                # FIXME: add the errors
                return render(request, 'setup/login.html', {'form': form})
        else:
            return render(request, 'setup/login.html', {'form': form})

def logout(request):
    request.session.flush()
    return redirect(home)

def error(request):
    return render(request, 'error.html', { 'error': "Not logged in yet."})

@never_cache
def note(request):
    mastodon = get_mastodon(request)
    notes = mastodon.notifications()
    return render(request, 'main/notifications.html',
                  {'notes': notes,'timeline': 'Notifications',
                   'fullbrutalism': fullbrutalism_p(request)})

@never_cache
def thread(request, id):
    mastodon = get_mastodon(request)
    context = mastodon.status_context(id)
    toot = mastodon.status(id)
    return render(request, 'main/thread.html',
                  {'context': context, 'toot': toot,
                   'fullbrutalism': fullbrutalism_p(request)})

@never_cache
def settings(request):
    if request.method == 'POST':
        form = SettingsForm(request.POST)
        if form.is_valid():
            request.session['fullbrutalism'] = form.cleaned_data['fullbrutalism']
            return redirect(home)
        else:
            return render(request, 'setup/settings.html',
                          {'form' : form, 'fullbrutalism': fullbrutalism_p(request)})
    else:
        form = SettingsForm(request.session)
        return render(request, 'setup/settings.html',
                      { 'form': form, 'fullbrutalism': fullbrutalism_p(request)})

@never_cache
def toot(request):
    if request.method == 'GET':
        form = PostForm()
        return render(request, 'main/post.html',
                      {'form': form,
                       'fullbrutalism': fullbrutalism_p(request)})
    elif request.method == 'POST':
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            mastodon = get_mastodon(request)

            # create media objects
            media_objects = []
            for index in range(1,5):
                if 'media_file_'+str(index) in request.FILES:
                    media_objects.append(
                        mastodon.media_post(request.FILES['media_file_'+str(index)]
                                            .temporary_file_path(),
                                            description=request.POST.get('media_text_'
                                                                         +str(index),
                                                                         None)))
            mastodon.status_post(status=form.cleaned_data['status'],
                                 visibility=form.cleaned_data['visibility'],
                                 spoiler_text=form.cleaned_data['spoiler_text'],
                                 media_ids=media_objects)
            return redirect(home)
        else:
            return render(request, 'main/post.html',
                          {'form': form,
                           'fullbrutalism': fullbrutalism_p(request)})
    else:
        return redirect(toot)

@never_cache
def reply(request, id):
    if request.method == 'GET':
        mastodon = get_mastodon(request)
        toot = mastodon.status(id)
        context = mastodon.status_context(id)
        initial_text = '@' + toot.account.acct + " "
        for mention in toot.mentions:
            initial_text +=('@' + mention.acct + " ")
        form = PostForm({'status': initial_text,
                         'visibility': toot.visibility,
                         'spoiler_text': toot.spoiler_text})
        return render(request, 'main/reply.html',
                      {'context': context, 'toot': toot, 'form': form, 'reply':True,
                       'fullbrutalism': fullbrutalism_p(request)})
    elif request.method == 'POST':
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            # create media objects
            mastodon = get_mastodon(request)
            # create media objects
            media_objects = []
            for index in range(1,5):
                if 'media_file_'+str(index) in request.FILES:
                    media_objects.append(
                        mastodon.media_post(request.FILES['media_file_'+str(index)]
                                            .temporary_file_path(),
                                            description=request.POST.get('media_text_'
                                                                         +str(index),
                                                                         None)))
            mastodon.status_post(status=form.cleaned_data['status'],
                                 visibility=form.cleaned_data['visibility'],
                                 spoiler_text=form.cleaned_data['spoiler_text'],
                                 in_reply_to_id=id)
            return redirect(thread, id)
        else:
            return render(request, 'main/reply.html',
                          {'context': context, 'toot': toot, 'form': form, 'reply': True,
                           'fullbrutalism': fullbrutalism_p(request)})
    else:
        return redirect(reply, id)

@never_cache
def fav(request, id):
    mastodon = get_mastodon(request)
    toot = mastodon.status(id)
    if request.method == 'POST':
        if not request.POST.get('cancel', None):
            if toot.favourited:
                mastodon.status_unfavourite(id)
            else:
                mastodon.status_favourite(id)
        return redirect(thread, id)
    else:
        return render(request, 'main/fav.html',
                      {"toot": toot,
                       'fullbrutalism': fullbrutalism_p(request)})

@never_cache
def boost(request, id):
    mastodon = get_mastodon(request)
    toot = mastodon.status(id)
    if request.method == 'POST':
        if not request.POST.get('cancel', None):
            if toot.reblogged:
                mastodon.status_unreblog(id)
            else:
                mastodon.status_reblog(id)
        return redirect(thread, id)
    else:
        return render(request, 'main/boost.html',
                      {"toot": toot,
                       "fullbrutalism": fullbrutalism_p(request)})
