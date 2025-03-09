from sqlalchemy import create_engine, Column, Integer, Table, MetaData
from sqlalchemy.dialects.postgresql import ENUM
metadata = MetaData()

gender_t = ENUM('male', 'female', 'other', name="gender_t")
education_stage_t = ENUM('university', 'high', 'other', name="education_stage_t")
identity_list_t = ENUM(
    'normal-student', 'citizen', 'experimental-educator',
    'other', 'parents', 'experimental-education-student', name="identity_list_t"
)

city_t = ENUM(
    'taipei_city', 'new_taipei_city', 'keelung_city', 'lianjiang_county', 'taoyuan_city',
    'hsinchu_city', 'hsinchu_county', 'miaoli_county', 'taichung_city', 'changhua_county',
    'yunlin_county', 'chiayi_county', 'chiayi_city', 'tainan_city', 'nantou_county',
    'kaohsiung_city', 'pingtung_county', 'hainan_island', 'penghu_county', 'kinmen_county',
    'yilan_county', 'hualien_county', 'taitung_county',
    'other',
    'online', 'tbd',
    name="city_t"
)


partnerEducationStep_t = ENUM(
    'high','other', 'university', name = "partner_education_step_t"
)

group_category_t = ENUM(
    'language',
    'math',
    'computer-science',
    'humanity',
    'nature-science',
    'art',
    'education',
    'life',
    'health',
    'business',
    'diversity',
    'learningtools',
    name = "group_category_t"
)

group_type_t  = ENUM (
    'study_group',
    'workshop',
    'project',
    'competition',
    'event',
    'club',
    'course',
    'internship',
    'other',
    name = "group_type_t"
)

want_to_do_list_t = ENUM(
    'interaction', 'do-project', 'make-group-class',
    'find-student', 'find-teacher', 'find-group', name="want_to_do_list_t"
)
age_t = ENUM(
    'preschool', 'elementary', 'high', 'university', name="age_t"
)

cost_t = ENUM('free', 'part', 'payment', name="cost_t")


group_participation_role_t = ENUM('Initiator', 'Participant', name="group_participation_role_t")
qualifications_t = ENUM(
    'low_income', 'discount', 'personal', 'double', 'three', 'four', name="qualifications_t"
)

day_t = ENUM(
    'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
    name = "day_enum"
)

motivation_t = ENUM(
    'driven_by_curiosity',
    'interest_and_passion',
    'self_challenge',
    'personal_growth',
    'career_development',
    'pursuing_education_or_qualifications',
    'social_recognition',
    'exploring_possibilities',
    'preparing_for_the_future',
    'innovation_and_development',
    'practical_needs',
    'inspired_by_events',
    'interpersonal_connections',
    'life_changes',
    'impact_on_society',
    'influenced_by_a_group',
    'others',
    name = "motivation_t"
)
strategy_t = ENUM(
    'data_collection_research_analysis',
    'book_reading',
    'watching_videos',
    'listening_to_podcasts',
    'examinations',
    'participating_in_competitions',
    'finding_study_partners',
    'joining_communities',
    'consulting_experts_and_scholars',
    'doing_projects',
    'initiating_actions',
    'field_internship',
    'organizing_events_or_courses',
    'attending_events_or_courses',
    'field_research',
    'conducting_interviews',
    'conducting_surveys',
    'others',
    name ="strategy_t"
)
outcome_t = ENUM(
    'building_websites',
    'managing_social_media',
    'writing_research_reports',
    'artistic_creation',
    'initiating_projects_or_organizations',
    'making_videos',
    'organizing_events',
    'teaching_courses',
    'participating_in_competitions',
    'others',
    name = "outcome_t"
)
