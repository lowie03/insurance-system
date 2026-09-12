/** Form options. These must match the backend's Literal values in schemas.py exactly. */

export const STATES = {
  "North Central": ["Benue", "FCT", "Kogi", "Kwara", "Nasarawa", "Niger", "Plateau"],
  "North East": ["Adamawa", "Bauchi", "Borno", "Gombe", "Taraba", "Yobe"],
  "North West": ["Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi", "Sokoto", "Zamfara"],
  "South East": ["Abia", "Anambra", "Ebonyi", "Enugu", "Imo"],
  "South South": ["Akwa Ibom", "Bayelsa", "Cross River", "Delta", "Edo", "Rivers"],
  "South West": ["Ekiti", "Lagos", "Ogun", "Ondo", "Osun", "Oyo"],
};

export const ZONE_OF_STATE = Object.fromEntries(
  Object.entries(STATES).flatMap(([zone, states]) => states.map((state) => [state, zone])),
);

/** Occupations the model saw in training, grouped so we can fill occupation_category automatically. */
export const OCCUPATIONS = [
  { value: "Trader", category: "Self-employed" },
  { value: "Business Owner", category: "Self-employed" },
  { value: "Artisan", category: "Self-employed" },
  { value: "Farmer", category: "Self-employed" },
  { value: "Commercial Driver", category: "Self-employed" },
  { value: "Civil Servant", category: "Public sector" },
  { value: "Teacher", category: "Public sector" },
  { value: "Banker", category: "Private salaried" },
  { value: "Software Engineer", category: "Private salaried" },
  { value: "Medical Doctor", category: "Private salaried" },
  { value: "Private Sector Staff", category: "Private salaried" },
  { value: "Student", category: "Dependent" },
  { value: "Unemployed", category: "Dependent" },
  { value: "Retired", category: "Retired" },
];

export const VEHICLE_TYPES = ["Motorcycle", "Tricycle", "Saloon Car", "SUV", "Bus"];

export const emptyProfile = {
  full_name: "", email: "", phone: "",
  gender: "", age: "", marital_status: "", dependents: 0,
  state: "", area_type: "", occupation: "", monthly_income_ngn: "",
  employer_hmo: false, smoker: false, pre_existing_condition: false,
  owns_vehicle: false, vehicle_type: "", vehicle_year: "", vehicle_value_ngn: "", vehicle_use: "",
  home_status: "", property_value_ngn: "", runs_shop: false,
  travelling_abroad: false, foreign_trips_per_year: 0,
  risk_appetite: "Medium",
};

const number = (value) => (value === "" || value === null ? null : Number(value));

/** Turn the form state into exactly what POST /quotes expects. */
export function toQuoteBody(form) {
  const occupation = OCCUPATIONS.find((o) => o.value === form.occupation);
  return {
    full_name: form.full_name.trim(),
    email: form.email.trim() || null,
    phone: form.phone.replace(/\s/g, "") || null,
    profile: {
      gender: form.gender,
      age: Number(form.age),
      marital_status: form.marital_status,
      dependents: Number(form.dependents),
      state: form.state,
      geo_zone: ZONE_OF_STATE[form.state],
      area_type: form.area_type,
      occupation: form.occupation,
      occupation_category: occupation?.category ?? "Self-employed",
      monthly_income_ngn: number(form.monthly_income_ngn),
      employer_hmo: form.employer_hmo,
      smoker: form.smoker,
      pre_existing_condition: form.pre_existing_condition,
      owns_vehicle: form.owns_vehicle,
      vehicle_type: form.owns_vehicle ? form.vehicle_type : null,
      vehicle_year: form.owns_vehicle ? number(form.vehicle_year) : null,
      vehicle_value_ngn: form.owns_vehicle ? number(form.vehicle_value_ngn) : null,
      vehicle_use: form.owns_vehicle ? form.vehicle_use : null,
      home_status: form.home_status,
      property_value_ngn: form.home_status === "Owner" ? number(form.property_value_ngn) : null,
      runs_shop: form.runs_shop,
      foreign_trips_per_year: form.travelling_abroad ? Number(form.foreign_trips_per_year || 1) : 0,
      risk_appetite: form.risk_appetite,
      owned_products: [],
    },
  };
}

/** Per-step validation. Returns { field: message } for anything the person still needs to fix. */
export function validateStep(step, form) {
  const errors = {};
  const required = (field, message) => { if (!form[field]) errors[field] = message; };

  if (step === 0) {
    if (form.full_name.trim().length < 2) errors.full_name = "Enter your name.";
    required("gender", "Choose one.");
    const age = Number(form.age);
    if (!form.age || age < 18 || age > 100) errors.age = "Enter an age between 18 and 100.";
    required("marital_status", "Choose one.");
  }
  if (step === 1) {
    required("state", "Choose your state.");
    required("area_type", "Choose one.");
    required("occupation", "Choose the closest match.");
  }
  if (step === 2) {
    if (form.monthly_income_ngn !== "" && Number(form.monthly_income_ngn) < 0)
      errors.monthly_income_ngn = "Income can't be negative.";
  }
  if (step === 3) {
    required("home_status", "Choose one.");
    if (form.owns_vehicle) {
      required("vehicle_type", "Choose the type.");
      required("vehicle_use", "Choose one.");
      const year = Number(form.vehicle_year);
      if (!form.vehicle_year || year < 1970) errors.vehicle_year = "Enter the year, e.g. 2018.";
      if (!form.vehicle_value_ngn || Number(form.vehicle_value_ngn) <= 0)
        errors.vehicle_value_ngn = "Roughly what is it worth today?";
    }
  }
  if (step === 4) {
    if (!form.email.trim()) errors.email = "We need an email to send your certificate.";
    else if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email.trim())) errors.email = "Check this email address.";
  }
  return errors;
}