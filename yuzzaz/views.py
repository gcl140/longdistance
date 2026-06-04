
from django.core.paginator import Paginator
from django.shortcuts import render
from django.urls import reverse
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import login as auth_login
from django.shortcuts import render, redirect
from django.contrib.auth import get_user_model, login as auth_login, logout as auth_logout
from django.contrib import messages
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.sites.shortcuts import get_current_site
from .tokens import account_activation_token
from .forms import UserRegistrationForm
from django.utils.timezone import now
from django.contrib.sites.shortcuts import get_current_site
from datetime import timedelta, datetime
from yuzzaz.forms import UserRegistrationForm, CustomUserForm
from django.contrib.auth.decorators import login_required, user_passes_test
from yuzzaz.tokens import account_activation_token

User = get_user_model()

staff_required = user_passes_test(lambda u: u.is_staff)

def landing(request):
    context = {}
    if request.user.is_authenticated:
        from parties.models import PartyInvite, WatchParty
        context["my_parties"] = WatchParty.objects.filter(
            members__user=request.user, ended_at__isnull=True
        ).distinct()[:10]
        context["invite_count"] = PartyInvite.objects.filter(
            recipient=request.user, status="pending"
        ).count()

        # A small "upcoming" snippet of the calendar — next few scheduled parties.
        from schedule.views import _user_scheduled_parties
        upcoming = [
            p for p in _user_scheduled_parties(request.user)
            if p.scheduled_for and p.scheduled_for >= now()
        ][:4]
        context["upcoming_parties"] = upcoming
    return render(request, 'yuzzaz/land.html', context)

def register(request):
    if request.method == "POST":
        form = UserRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()

            # Send activation email
            current_site = get_current_site(request)
            message = render_to_string("yuzzaz/activate_account.html", {
                'user': user,
                'domain': current_site.domain,
                'protocol': 'https' if request.is_secure() else 'http',
                'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                'token': account_activation_token.make_token(user),
                'current_year': datetime.now().year,
            })
            email = EmailMessage("Activate your user account", message, to=[user.email])
            email.content_subtype = "html"
            email.send()

            # Store session for resend logic
            request.session['inactive_user_email'] = user.email
            # request.session['email_sent_time'] = datetime.now().isoformat()
            request.session['email_sent_time'] = now().isoformat()


            messages.success(request, f"Dear {user.first_name}, we have sent an activation link to your email. Please check your email to complete registration (Remember to check your spam too, you can't proceed without that email).")
            return redirect('activation_sent')
    else:
        form = UserRegistrationForm()

    return render(request, 'yuzzaz/register.html', {'form': form})

def activate(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if not user:
        messages.error(request, "Invalid activation link.")
        return redirect('home')

    if user.is_active:
        messages.info(request, "Account already activated. You can log in.")
        return redirect('login')

    if not account_activation_token.check_token(user, token):
        messages.error(request, "Activation link is invalid or expired.")
        return redirect('home')

    user.is_active = True
    user.save()
    messages.success(request, "Thank you for confirming your email. Your account is now activated, and you can now log in.")
    return redirect('login')

def activation_sent(request):
    email = request.session.get('inactive_user_email')
    if not email:
        messages.warning(request, "No activation request found.")
        return redirect('login')  # Use your standard register route

    if not request.session.get('email_sent_time'):
        request.session['email_sent_time'] = now().isoformat()

    return render(request, 'yuzzaz/activation_sent.html', {
        'email': email,
        'can_resend_at': now() + timedelta(seconds=90),
    })

def resend_activation_email(request):
    email = request.session.get('inactive_user_email')
    sent_time = request.session.get('email_sent_time')

    if not email or not sent_time:
        messages.error(request, "Session expired. Please register again.")
        return redirect('register')

    sent_time = datetime.fromisoformat(sent_time)

    user = User.objects.filter(email=email, is_active=False).first()
    if user:
        current_site = get_current_site(request)
        message = render_to_string("yuzzaz/activate_account.html", {
            'user': user,
            'domain': current_site.domain,
            'protocol': 'https' if request.is_secure() else 'http',
            'uid': urlsafe_base64_encode(force_bytes(user.pk)),
            'token': account_activation_token.make_token(user),
            'current_year': datetime.now().year,
        })
        email_obj = EmailMessage("Activate your user account", message, to=[user.email])
        email_obj.content_subtype = "html"
        email_obj.send()

        request.session['email_sent_time'] = now().isoformat()
        messages.success(request, "A new activation link has been sent.")
    else:
        messages.error(request, "No inactive account found with that email.")

    return redirect('activation_sent')


def login(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']

        user = User.objects.filter(email=username).first()
        if user and user.check_password(password):
            if not user.is_active:
                request.session['inactive_user_email'] = user.email
                request.session['email_sent_time'] = now().isoformat()
                messages.warning(request, "Your account is not activated. Please check your email or resend the activation link.")
                return redirect('activation_sent')

            # auth_login(request, user)
            auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, "You have successfully logged in.")
            if user.is_staff:
                return redirect('catalog:library')  # staff manage the movie library
            else:
                return redirect('home')  # Standard redirect — adjust to your default user landing page

        messages.error(request, "Invalid credentials, please try again.")

    return render(request, 'yuzzaz/login.html')

def logout(request):
    auth_logout(request)
    messages.success(request, "You have successfully logged out.")
    return redirect('login')


@login_required
def profile(request):
    user = request.user  # Get the current logged-in user
    if request.method == 'POST':
        form = CustomUserForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            print("called")
            form.save()
            messages.success(request, "Your profile has been updated!")
            return redirect('profile')  # Redirect to the same page
        else:
            print(form.errors)

    else:
        form = CustomUserForm(instance=user)

    return render(request, 'yuzzaz/profile.html', {
        'user': user,
        'form': form,
    })


def company_profile(request):
    context = {        
    }
    return render(request, 'yuzzaz/company_profile.html', context)

def logout_and_login(request):
    auth_logout(request)
    return redirect(f"{reverse('social:begin', args=['google-oauth2'])}?next=/profile/")



@login_required
def edit_profile(request):
    if request.method == 'POST':
        form = CustomUserForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('view_profile', id=request.user.id)
    else:
        form = CustomUserForm(instance=request.user)

    return render(request, 'yuzzaz/partials/edit_profile_modal.html', {'form': form, 'viewing_user': request.user})
    
    

def custom_404_view(request, exception):
    return render(request, 'yuzzaz/404.html', status=404)


def contact(request):
    form = ContactForm()
    return render(request, 'partials/contact.html', {'form': form})


def news(request):
    news_list = New.objects.all().order_by('-updated_at')
    paginator = Paginator(news_list, 5)  # 5 news items per page

    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
    }

    return render(request, 'partials/news.html', context)


def journey(request):
    images_qs = Gallery.objects.all()
    events_qs = UpcomingEvent.objects.all().order_by('-event_date')
    faq_qs = FAQ.objects.all()
    team_qs = TeamMember.objects.all()


    images_paginator = Paginator(images_qs, 6)
    events_paginator = Paginator(events_qs, 5)
    faq_paginator = Paginator(faq_qs, 5)
    team_paginator = Paginator(team_qs, 4)

    images_page_number = request.GET.get('images_page')
    events_page_number = request.GET.get('events_page')
    faq_page_number = request.GET.get('faq_page')
    team_page_number = request.GET.get('team_page')
    images_page = images_paginator.get_page(images_page_number)
    events_page = events_paginator.get_page(events_page_number)
    faq_page = faq_paginator.get_page(faq_page_number)
    team_page = team_paginator.get_page(team_page_number)

    context = {
        'images_page': images_page,
        'events_page': events_page,
        'faq_page': faq_page,
        'team_page': team_page,
    }
    return render(request, 'partials/journey.html', context)


@staff_required
def admin_dashboard(request):
    """A lightweight staff hub: stats, open movie requests with quick actions,
    and shortcuts. Distinct from Django's /admin/ — this is the day-to-day panel.
    """
    from catalog.models import Movie, MovieRequest
    from catalog.views import purge_stale_requests
    from parties.models import WatchParty

    purge_stale_requests()  # keep the table tidy on each visit

    open_requests = (
        MovieRequest.objects.filter(status__in=("pending", "approved"))
        .select_related("requester")
    )
    recent_requests = (
        MovieRequest.objects.filter(status__in=("fulfilled", "rejected"))
        .select_related("fulfilled_movie")[:10]
    )
    stats = {
        "movies": Movie.objects.count(),
        "pending_requests": MovieRequest.objects.filter(status="pending").count(),
        "active_parties": WatchParty.objects.filter(ended_at__isnull=True).count(),
        "users": User.objects.count(),
    }
    return render(request, "yuzzaz/admin_dashboard.html", {
        "open_requests": open_requests,
        "recent_requests": recent_requests,
        "stats": stats,
    })