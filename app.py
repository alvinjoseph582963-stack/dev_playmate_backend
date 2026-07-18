# =====================================================
#  PlayMate – Flask REST API Backend
#  Run: python app.py
#  Requires: pip install -r requirements.txt
# =====================================================

from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import (
    JWTManager, create_access_token,
    jwt_required, get_jwt_identity, verify_jwt_in_request
)
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os, uuid

load_dotenv()

# ─── APP SETUP ──────────────────────────────────────
app = Flask(__name__, static_folder='..', static_url_path='')
CORS(app, resources={r"/api/*": {"origins": "*"}})

app.config.update(
    SQLALCHEMY_DATABASE_URI=os.getenv(
        'DATABASE_URL',
        'mysql+pymysql://root:password@localhost/playmate_db'
    ),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    JWT_SECRET_KEY=os.getenv('JWT_SECRET_KEY', 'playmate-super-secret-key-2025'),
    JWT_ACCESS_TOKEN_EXPIRES=timedelta(days=30),
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16 MB
)

db  = SQLAlchemy(app)
jwt = JWTManager(app)

# ─── MODELS ─────────────────────────────────────────

class User(db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name          = db.Column(db.String(100), nullable=False)
    email         = db.Column(db.String(150), nullable=False, unique=True)
    phone         = db.Column(db.String(15),  nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    profile_photo = db.Column(db.Text, nullable=True)
    is_active     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at    = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    venues    = db.relationship('Venue',      backref='owner', lazy=True, cascade='all, delete-orphan')
    bookings  = db.relationship('SlotMember', backref='user',  lazy=True, cascade='all, delete-orphan')


class Venue(db.Model):
    __tablename__ = 'venues'
    id             = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id       = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    name           = db.Column(db.String(150), nullable=False)
    sport_type     = db.Column(db.String(50),  nullable=False)
    location       = db.Column(db.String(255), nullable=False)
    description    = db.Column(db.Text)
    price_per_slot = db.Column(db.Float, default=0.0)
    is_active      = db.Column(db.Boolean, default=True)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)

    photos    = db.relationship('VenuePhoto',   backref='venue', lazy=True, cascade='all, delete-orphan', order_by='VenuePhoto.sort_order')
    amenities = db.relationship('VenueAmenity', backref='venue', lazy=True, cascade='all, delete-orphan')
    slots     = db.relationship('Slot',         backref='venue', lazy=True, cascade='all, delete-orphan')


class VenuePhoto(db.Model):
    __tablename__ = 'venue_photos'
    id         = db.Column(db.Integer, primary_key=True, autoincrement=True)
    venue_id   = db.Column(db.String(36), db.ForeignKey('venues.id'), nullable=False)
    photo_url  = db.Column(db.Text, nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class VenueAmenity(db.Model):
    __tablename__ = 'venue_amenities'
    id       = db.Column(db.Integer, primary_key=True, autoincrement=True)
    venue_id = db.Column(db.String(36), db.ForeignKey('venues.id'), nullable=False)
    amenity  = db.Column(db.String(100), nullable=False)


class Slot(db.Model):
    __tablename__ = 'slots'
    id          = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    venue_id    = db.Column(db.String(36), db.ForeignKey('venues.id'), nullable=False)
    slot_date   = db.Column(db.Date, nullable=False)
    start_time  = db.Column(db.Time, nullable=False)
    end_time    = db.Column(db.Time, nullable=False)
    min_members = db.Column(db.Integer, default=2)
    max_members = db.Column(db.Integer, default=10)
    price       = db.Column(db.Float, default=0.0)
    status      = db.Column(db.String(20), default='open')  # open | locked | cancelled | completed
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    members = db.relationship('SlotMember', backref='slot', lazy=True, cascade='all, delete-orphan')


class SlotMember(db.Model):
    __tablename__ = 'slot_members'
    id        = db.Column(db.Integer, primary_key=True, autoincrement=True)
    slot_id   = db.Column(db.String(36), db.ForeignKey('slots.id'), nullable=False)
    user_id   = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('slot_id', 'user_id', name='uq_slot_user'),)


# ─── SERIALIZERS ────────────────────────────────────

def user_to_dict(user, private=False):
    d = {
        'id':            user.id,
        'name':          user.name,
        'email':         user.email,
        'profile_photo': user.profile_photo,
        'created_at':    user.created_at.isoformat() if user.created_at else None,
    }
    if private:
        d['phone'] = user.phone
    return d


def venue_to_dict(venue):
    return {
        'id':             venue.id,
        'owner_id':       venue.owner_id,
        'name':           venue.name,
        'sportType':      venue.sport_type,
        'location':       venue.location,
        'description':    venue.description,
        'pricePerSlot':   venue.price_per_slot,
        'photos':         [p.photo_url for p in venue.photos],
        'amenities':      [a.amenity  for a in venue.amenities],
        'created_at':     venue.created_at.isoformat() if venue.created_at else None,
    }


def slot_to_dict(slot, viewer_id=None, include_members=False):
    member_ids = [m.user_id for m in slot.members]
    d = {
        'id':          slot.id,
        'venueId':     slot.venue_id,
        'date':        slot.slot_date.isoformat()         if slot.slot_date  else None,
        'startTime':   slot.start_time.strftime('%H:%M') if slot.start_time else None,
        'endTime':     slot.end_time.strftime('%H:%M')   if slot.end_time   else None,
        'minMembers':  slot.min_members,
        'maxMembers':  slot.max_members,
        'price':       slot.price,
        'status':      slot.status,
        'members':     member_ids,           # list of user IDs (for frontend compat)
        'memberCount': len(member_ids),
        'isJoined':    viewer_id in member_ids if viewer_id else False,
    }
    if include_members:
        details = []
        for m in slot.members:
            u = db.session.get(User, m.user_id)
            if u:
                details.append({
                    'id':            u.id,
                    'name':          u.name,
                    'email':         u.email,
                    'phone':         u.phone,
                    'profile_photo': u.profile_photo,
                    'joined_at':     m.joined_at.isoformat() if m.joined_at else None,
                })
        d['memberDetails'] = details
    return d


# ─── HELPERS ────────────────────────────────────────

def optional_jwt_identity():
    """Return user id from JWT if present, else None."""
    try:
        verify_jwt_in_request(optional=True)
        return get_jwt_identity()
    except Exception:
        return None


def process_expired():
    """Cancel/complete past open slots."""
    now = datetime.utcnow()
    changed = False
    for slot in Slot.query.filter_by(status='open').all():
        end_dt = datetime.combine(slot.slot_date, slot.end_time)
        if end_dt < now:
            cnt = SlotMember.query.filter_by(slot_id=slot.id).count()
            slot.status = 'completed' if cnt >= slot.min_members else 'cancelled'
            changed = True
    if changed:
        db.session.commit()


# ─── STATIC FRONTEND ────────────────────────────────

@app.route('/')
def serve_index():
    return send_from_directory('..', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('..', filename)


# ═══════════════════════════════════════════════════
#  AUTH ROUTES
# ═══════════════════════════════════════════════════

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    name          = data.get('name', '').strip()
    email         = data.get('email', '').strip().lower()
    phone         = data.get('phone', '').strip()
    password      = data.get('password', '')
    profile_photo = data.get('profile_photo')

    if not all([name, email, phone, password]):
        return jsonify({'error': 'All fields are required'}), 400
    if len(phone) != 10 or not phone.isdigit():
        return jsonify({'error': 'Phone must be exactly 10 digits'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already registered'}), 409

    user = User(
        name=name, email=email, phone=phone,
        password_hash=generate_password_hash(password),
        profile_photo=profile_photo,
    )
    db.session.add(user)
    db.session.commit()

    token = create_access_token(identity=user.id)
    return jsonify({'token': token, 'user': user_to_dict(user, private=True)}), 201


@app.route('/api/auth/login', methods=['POST'])
def login():
    data     = request.get_json() or {}
    email    = data.get('email', '').strip().lower()
    password = data.get('password', '')

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Invalid email or password'}), 401

    token = create_access_token(identity=user.id)
    return jsonify({'token': token, 'user': user_to_dict(user, private=True)}), 200


@app.route('/api/auth/me', methods=['GET'])
@jwt_required()
def get_me():
    user = db.session.get(User, get_jwt_identity())
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify({'user': user_to_dict(user, private=True)}), 200


# ═══════════════════════════════════════════════════
#  USER ROUTES
# ═══════════════════════════════════════════════════

@app.route('/api/users/me', methods=['PUT'])
@jwt_required()
def update_profile():
    user = db.session.get(User, get_jwt_identity())
    if not user:
        return jsonify({'error': 'User not found'}), 404

    data = request.get_json() or {}
    if 'name' in data and data['name'].strip():
        user.name = data['name'].strip()
    if 'phone' in data:
        phone = data['phone'].strip()
        if len(phone) != 10 or not phone.isdigit():
            return jsonify({'error': 'Phone must be exactly 10 digits'}), 400
        user.phone = phone
    if 'profile_photo' in data:
        user.profile_photo = data['profile_photo']

    db.session.commit()
    return jsonify({'user': user_to_dict(user, private=True)}), 200


@app.route('/api/users/me/slots', methods=['GET'])
@jwt_required()
def my_slots():
    uid = get_jwt_identity()
    result = []
    for m in SlotMember.query.filter_by(user_id=uid).all():
        slot = db.session.get(Slot, m.slot_id)
        if not slot:
            continue
        sd = slot_to_dict(slot, viewer_id=uid)
        venue = db.session.get(Venue, slot.venue_id)
        if venue:
            sd['venueName']   = venue.name
            sd['venueLocation'] = venue.location
            sd['sportType']   = venue.sport_type
            sd['venuePhoto']  = venue.photos[0].photo_url if venue.photos else None
        result.append(sd)
    return jsonify({'slots': result}), 200


@app.route('/api/users/me/venues', methods=['GET'])
@jwt_required()
def my_venues():
    uid    = get_jwt_identity()
    venues = Venue.query.filter_by(owner_id=uid).all()
    result = []
    for v in venues:
        vd = venue_to_dict(v)
        vd['openSlots']  = Slot.query.filter_by(venue_id=v.id, status='open').count()
        vd['totalSlots'] = Slot.query.filter_by(venue_id=v.id).count()
        result.append(vd)
    return jsonify({'venues': result}), 200


# ═══════════════════════════════════════════════════
#  VENUE ROUTES
# ═══════════════════════════════════════════════════

@app.route('/api/venues', methods=['GET'])
def get_venues():
    q     = request.args.get('q', '').strip()
    sport = request.args.get('sport', 'all')

    qr = Venue.query.filter_by(is_active=True)
    if sport and sport != 'all':
        qr = qr.filter_by(sport_type=sport)
    if q:
        like = f'%{q}%'
        qr = qr.filter(db.or_(
            Venue.name.ilike(like),
            Venue.location.ilike(like),
            Venue.description.ilike(like),
        ))

    venues = qr.order_by(Venue.created_at.desc()).all()
    result = []
    for v in venues:
        vd = venue_to_dict(v)
        vd['openSlots']  = Slot.query.filter_by(venue_id=v.id, status='open').count()
        vd['totalSlots'] = Slot.query.filter_by(venue_id=v.id).count()
        result.append(vd)
    return jsonify({'venues': result}), 200


@app.route('/api/venues/<venue_id>', methods=['GET'])
def get_venue(venue_id):
    venue = db.session.get(Venue, venue_id)
    if not venue:
        return jsonify({'error': 'Venue not found'}), 404
    vd    = venue_to_dict(venue)
    owner = db.session.get(User, venue.owner_id)
    vd['owner']      = user_to_dict(owner, private=False) if owner else None
    vd['ownerPhone'] = owner.phone  if owner else None
    vd['ownerEmail'] = owner.email  if owner else None
    return jsonify({'venue': vd}), 200


@app.route('/api/venues', methods=['POST'])
@jwt_required()
def create_venue():
    uid  = get_jwt_identity()
    data = request.get_json() or {}

    name        = data.get('name', '').strip()
    sport_type  = data.get('sport_type', '').strip()
    location    = data.get('location', '').strip()
    description = data.get('description', '').strip()
    photos      = data.get('photos', [])
    amenities   = data.get('amenities', [])
    price       = float(data.get('price_per_slot', 0))

    if not all([name, sport_type, location]):
        return jsonify({'error': 'Name, sport type and location are required'}), 400

    venue = Venue(
        owner_id=uid, name=name, sport_type=sport_type,
        location=location, description=description, price_per_slot=price,
    )
    db.session.add(venue)
    db.session.flush()

    for i, url in enumerate(photos):
        db.session.add(VenuePhoto(venue_id=venue.id, photo_url=url, sort_order=i))
    for a in amenities:
        if a.strip():
            db.session.add(VenueAmenity(venue_id=venue.id, amenity=a.strip()))

    db.session.commit()
    return jsonify({'venue': venue_to_dict(venue)}), 201


@app.route('/api/venues/<venue_id>', methods=['DELETE'])
@jwt_required()
def delete_venue(venue_id):
    uid   = get_jwt_identity()
    venue = db.session.get(Venue, venue_id)
    if not venue:
        return jsonify({'error': 'Venue not found'}), 404
    if venue.owner_id != uid:
        return jsonify({'error': 'Not authorized'}), 403
    db.session.delete(venue)
    db.session.commit()
    return jsonify({'message': 'Venue deleted'}), 200


# ═══════════════════════════════════════════════════
#  SLOT ROUTES
# ═══════════════════════════════════════════════════

@app.route('/api/venues/<venue_id>/slots', methods=['GET'])
def get_slots(venue_id):
    viewer_id = optional_jwt_identity()
    slots = (Slot.query
             .filter_by(venue_id=venue_id)
             .order_by(Slot.slot_date, Slot.start_time)
             .all())
    return jsonify({'slots': [slot_to_dict(s, viewer_id=viewer_id) for s in slots]}), 200


@app.route('/api/venues/<venue_id>/slots', methods=['POST'])
@jwt_required()
def create_slot(venue_id):
    uid   = get_jwt_identity()
    venue = db.session.get(Venue, venue_id)
    if not venue:
        return jsonify({'error': 'Venue not found'}), 404
    if venue.owner_id != uid:
        return jsonify({'error': 'Only the venue owner can add slots'}), 403

    data       = request.get_json() or {}
    date_str   = data.get('date')
    start_str  = data.get('start_time')
    end_str    = data.get('end_time')
    min_m      = int(data.get('min_members', 2))
    max_m      = int(data.get('max_members', 10))
    price      = float(data.get('price', 0))

    if not all([date_str, start_str, end_str]):
        return jsonify({'error': 'Date, start_time and end_time are required'}), 400
    if min_m > max_m:
        return jsonify({'error': 'min_members cannot exceed max_members'}), 400

    slot = Slot(
        venue_id=venue_id,
        slot_date=datetime.strptime(date_str, '%Y-%m-%d').date(),
        start_time=datetime.strptime(start_str, '%H:%M').time(),
        end_time=datetime.strptime(end_str,   '%H:%M').time(),
        min_members=min_m, max_members=max_m, price=price, status='open',
    )
    db.session.add(slot)
    db.session.commit()
    return jsonify({'slot': slot_to_dict(slot)}), 201


@app.route('/api/slots/<slot_id>', methods=['DELETE'])
@jwt_required()
def delete_slot(slot_id):
    uid   = get_jwt_identity()
    slot  = db.session.get(Slot, slot_id)
    if not slot:
        return jsonify({'error': 'Slot not found'}), 404
    venue = db.session.get(Venue, slot.venue_id)
    if not venue or venue.owner_id != uid:
        return jsonify({'error': 'Not authorized'}), 403
    db.session.delete(slot)
    db.session.commit()
    return jsonify({'message': 'Slot deleted'}), 200


@app.route('/api/slots/<slot_id>/join', methods=['POST'])
@jwt_required()
def join_slot(slot_id):
    uid  = get_jwt_identity()
    slot = db.session.get(Slot, slot_id)
    if not slot:
        return jsonify({'error': 'Slot not found'}), 404
    if slot.status == 'cancelled':
        return jsonify({'error': 'This slot has been cancelled'}), 400
    if slot.status == 'locked':
        return jsonify({'error': 'This slot is fully booked'}), 400

    if SlotMember.query.filter_by(slot_id=slot_id, user_id=uid).first():
        return jsonify({'error': 'You have already joined this slot'}), 400

    cnt = SlotMember.query.filter_by(slot_id=slot_id).count()
    if cnt >= slot.max_members:
        return jsonify({'error': 'Slot is full'}), 400

    db.session.add(SlotMember(slot_id=slot_id, user_id=uid))
    if cnt + 1 >= slot.max_members:
        slot.status = 'locked'
    db.session.commit()

    return jsonify({
        'message': 'Joined successfully',
        'slot': slot_to_dict(slot, viewer_id=uid),
    }), 200


@app.route('/api/slots/<slot_id>/leave', methods=['POST'])
@jwt_required()
def leave_slot(slot_id):
    uid  = get_jwt_identity()
    slot = db.session.get(Slot, slot_id)
    if not slot:
        return jsonify({'error': 'Slot not found'}), 404
    if slot.status == 'locked':
        return jsonify({'error': 'Cannot leave a locked slot. Contact the venue owner.'}), 400

    member = SlotMember.query.filter_by(slot_id=slot_id, user_id=uid).first()
    if not member:
        return jsonify({'error': 'You are not in this slot'}), 400

    db.session.delete(member)
    db.session.commit()
    return jsonify({'message': 'Left slot', 'slot': slot_to_dict(slot, viewer_id=uid)}), 200


@app.route('/api/slots/<slot_id>/members', methods=['GET'])
@jwt_required()
def get_slot_members(slot_id):
    uid   = get_jwt_identity()
    slot  = db.session.get(Slot, slot_id)
    if not slot:
        return jsonify({'error': 'Slot not found'}), 404
    venue = db.session.get(Venue, slot.venue_id)
    if not venue or venue.owner_id != uid:
        return jsonify({'error': 'Only the venue owner can view member contacts'}), 403
    return jsonify({'slot': slot_to_dict(slot, viewer_id=uid, include_members=True)}), 200


# ═══════════════════════════════════════════════════
#  UTILITY ROUTES
# ═══════════════════════════════════════════════════

@app.route('/api/stats', methods=['GET'])
def stats():
    return jsonify({
        'venues':     Venue.query.filter_by(is_active=True).count(),
        'open_slots': Slot.query.filter_by(status='open').count(),
        'players':    User.query.filter_by(is_active=True).count(),
    }), 200


@app.route('/api/admin/process-slots', methods=['POST'])
def admin_process_slots():
    process_expired()
    return jsonify({'message': 'Processed'}), 200


# ─── SEED DATA ──────────────────────────────────────

def seed():
    if User.query.first():
        return  # already seeded

    u1 = User(name='Arjun Mehta',  email='arjun@demo.com', phone='9876543210', password_hash=generate_password_hash('demo123'))
    u2 = User(name='Priya Sharma', email='priya@demo.com', phone='9123456789', password_hash=generate_password_hash('demo123'))
    u3 = User(name='Karan Singh',  email='karan@demo.com', phone='9988776655', password_hash=generate_password_hash('demo123'))
    u4 = User(name='Neha Patel',   email='neha@demo.com',  phone='9871234567', password_hash=generate_password_hash('demo123'))
    db.session.add_all([u1, u2, u3, u4])
    db.session.flush()

    venues_data = [
        dict(owner_id=u1.id, name='GoalPost Turf Arena',        sport_type='Football',   location='Koramangala, Bangalore', description='Premium 5-a-side football turf with floodlights and changing rooms.', price_per_slot=500,
             photos=['https://images.unsplash.com/photo-1529900748604-07564a03e7a6?w=800&q=80','https://images.unsplash.com/photo-1459865264687-595d652de67e?w=800&q=80'],
             amenities=['Floodlights','Changing Rooms','Parking','Equipment Rental','Canteen']),
        dict(owner_id=u2.id, name='Smash Point Badminton Club',  sport_type='Badminton',  location='Indiranagar, Bangalore', description='Olympic-grade synthetic courts with LED lighting.', price_per_slot=300,
             photos=['https://images.unsplash.com/photo-1626224583764-f87db24ac4ea?w=800&q=80'],
             amenities=['LED Lighting','Shuttle Service','Racket Rental','Water Cooler']),
        dict(owner_id=u3.id, name='Slam Dunk Basketball Court',  sport_type='Basketball', location='HSR Layout, Bangalore',  description='Full-size NBA-standard hardwood basketball court.', price_per_slot=400,
             photos=['https://images.unsplash.com/photo-1546519638-68e109498ffc?w=800&q=80'],
             amenities=['Score Board','Water Cooler','Parking','First Aid']),
        dict(owner_id=u4.id, name='Cricket Premier Ground',      sport_type='Cricket',    location='Whitefield, Bangalore',  description='Well-maintained pitch with nets and spectator seating.', price_per_slot=600,
             photos=['https://images.unsplash.com/photo-1531415074968-036ba1b575da?w=800&q=80'],
             amenities=['Practice Nets','Equipment Rental','Seating','Parking']),
    ]

    venue_objs = []
    for vd in venues_data:
        v = Venue(owner_id=vd['owner_id'], name=vd['name'], sport_type=vd['sport_type'],
                  location=vd['location'], description=vd['description'], price_per_slot=vd['price_per_slot'])
        db.session.add(v)
        db.session.flush()
        for i, url in enumerate(vd['photos']):
            db.session.add(VenuePhoto(venue_id=v.id, photo_url=url, sort_order=i))
        for a in vd['amenities']:
            db.session.add(VenueAmenity(venue_id=v.id, amenity=a))
        venue_objs.append(v)
    db.session.flush()

    from datetime import date, timedelta as td
    tomorrow = date.today() + td(days=1)
    day3     = date.today() + td(days=2)
    day4     = date.today() + td(days=3)

    from datetime import time
    slots_data = [
        dict(venue_id=venue_objs[0].id, slot_date=tomorrow, start_time=time(6,0),  end_time=time(7,0),   min_members=6,  max_members=10, price=500),
        dict(venue_id=venue_objs[0].id, slot_date=tomorrow, start_time=time(18,0), end_time=time(19,0),  min_members=6,  max_members=10, price=500),
        dict(venue_id=venue_objs[0].id, slot_date=day3,     start_time=time(7,0),  end_time=time(8,0),   min_members=6,  max_members=14, price=500),
        dict(venue_id=venue_objs[1].id, slot_date=tomorrow, start_time=time(8,0),  end_time=time(9,0),   min_members=2,  max_members=4,  price=300),
        dict(venue_id=venue_objs[1].id, slot_date=day3,     start_time=time(10,0), end_time=time(11,0),  min_members=2,  max_members=4,  price=300),
        dict(venue_id=venue_objs[2].id, slot_date=day3,     start_time=time(7,0),  end_time=time(8,30),  min_members=5,  max_members=10, price=400),
        dict(venue_id=venue_objs[2].id, slot_date=day4,     start_time=time(17,0), end_time=time(18,30), min_members=5,  max_members=10, price=400),
        dict(venue_id=venue_objs[3].id, slot_date=day3,     start_time=time(6,0),  end_time=time(8,0),   min_members=10, max_members=22, price=600),
        dict(venue_id=venue_objs[3].id, slot_date=day4,     start_time=time(16,0), end_time=time(18,0),  min_members=10, max_members=22, price=600),
    ]
    slot_objs = []
    for sd in slots_data:
        s = Slot(**sd)
        db.session.add(s)
        db.session.flush()
        slot_objs.append(s)

    # Add some members
    pairs = [(0,u2.id),(0,u3.id),(0,u4.id),(3,u1.id),(5,u2.id),(5,u4.id)]
    for si, uid in pairs:
        db.session.add(SlotMember(slot_id=slot_objs[si].id, user_id=uid))

    db.session.commit()
    print('✅ Demo data seeded!')


# ─── ENTRY POINT ────────────────────────────────────

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        seed()
    app.run(debug=True, host='0.0.0.0', port=5000)
