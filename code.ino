#include <Servo.h>

// Servo objects
Servo smallServo;  // Scans flame sensor
Servo bigServo;    // Directs pump nozzle

// Motor pins (L293D)
const int enLeft = 5;   // PWM for left motors
const int inLeft1 = 4;  // Left motor forward
const int inLeft2 = 3;  // Left motor backward
const int enRight = 9;  // PWM for right motors
const int inRight1 = 7; // Right motor forward
const int inRight2 = 6; // Right motor backward

// Sensor pins
const int flamePin = 2;   // Flame sensor digital out (assuming active LOW)
const int trigPin = A0;   // Ultrasonic trigger
const int echoPin = A1;   // Ultrasonic echo
const int soilPin = A2;   // Soil moisture analog

// Output pins
const int ledPin = 12;    // Red LED for flame detection
const int pumpPin = 13;   // Relay for pump control

// Variables
int scanPos = 90;         // Small servo position (center)
char mode = 'N';          // Default: Normal mode
unsigned long lastSoil = 0; // Last soil reading time
unsigned long lastDist = 0; // Last distance send time

// Get distance from ultrasonic sensor (cm)
long getDistance() {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  long duration = pulseIn(echoPin, HIGH, 30000); // Timeout ~5m
  if (duration == 0) return 400; // Max range if no echo
  return duration * 0.034 / 2;
}

// Motor control functions
void stopMotors() {
  analogWrite(enLeft, 0);
  analogWrite(enRight, 0);
  digitalWrite(inLeft1, LOW);
  digitalWrite(inLeft2, LOW);
  digitalWrite(inRight1, LOW);
  digitalWrite(inRight2, LOW);
}

void moveForward() {
  long dist = getDistance();
  if (dist < 20) { // Stop if obstacle <20cm
    stopMotors();
    return;
  }
  digitalWrite(inLeft1, HIGH);
  digitalWrite(inLeft2, LOW);
  digitalWrite(inRight1, HIGH);
  digitalWrite(inRight2, LOW);
  analogWrite(enLeft, 150);  // PWM speed (0-255)
  analogWrite(enRight, 150);
}

void moveBackward() {
  digitalWrite(inLeft1, LOW);
  digitalWrite(inLeft2, HIGH);
  digitalWrite(inRight1, LOW);
  digitalWrite(inRight2, HIGH);
  analogWrite(enLeft, 150);
  analogWrite(enRight, 150);
}

void turnLeft() {
  digitalWrite(inLeft1, LOW);
  digitalWrite(inLeft2, HIGH);
  digitalWrite(inRight1, HIGH);
  digitalWrite(inRight2, LOW);
  analogWrite(enLeft, 150);
  analogWrite(enRight, 150);
}

void turnRight() {
  digitalWrite(inLeft1, HIGH);
  digitalWrite(inLeft2, LOW);
  digitalWrite(inRight1, LOW);
  digitalWrite(inRight2, HIGH);
  analogWrite(enLeft, 150);
  analogWrite(enRight, 150);
}

void activatePump() {
  digitalWrite(pumpPin, HIGH); // Relay on (adjust if active LOW)
}

void deactivatePump() {
  digitalWrite(pumpPin, LOW);
}

void setup() {
  // Initialize serial
  Serial.begin(9600);
  
  // Motor pins
  pinMode(enLeft, OUTPUT);
  pinMode(inLeft1, OUTPUT);
  pinMode(inLeft2, OUTPUT);
  pinMode(enRight, OUTPUT);
  pinMode(inRight1, OUTPUT);
  pinMode(inRight2, OUTPUT);
  
  // Sensor pins
  pinMode(flamePin, INPUT);
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  pinMode(soilPin, INPUT);
  
  // Output pins
  pinMode(ledPin, OUTPUT);
  pinMode(pumpPin, OUTPUT);
  digitalWrite(pumpPin, LOW); // Pump off
  
  // Servos
  smallServo.attach(11);
  bigServo.attach(10);
  smallServo.write(90);      // Center scanning servo
  bigServo.write(90);        // Center nozzle servo
  
  // Initial state
  stopMotors();
  Serial.println("Arduino Ready. Send 'A' for Auto, 'G' for Gesture, 'N' for Normal.");
}

void loop() {
  // Handle serial commands
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    if (cmd == 'A' || cmd == 'G' || cmd == 'N') {
      mode = cmd;
      Serial.println(String("Mode: ") + mode);
      if (mode != 'A') {
        smallServo.write(90); // Reset scan in non-Auto modes
        stopMotors();
        deactivatePump();
      }
    } else if (mode != 'A') { // Process commands in Gesture/Normal modes
      switch (cmd) {
        case 'F': moveForward(); break;
        case 'B': moveBackward(); break;
        case 'L': turnLeft(); break;
        case 'R': turnRight(); break;
        case 'S': stopMotors(); break;
        case 'P': activatePump(); break;
        default: break; // Ignore invalid commands
      }
    } else if (cmd == 'D') { // Send distance on request
      long dist = getDistance();
      Serial.println("Dist:" + String(dist));
    }
  }
  
  // Send soil moisture every 5 seconds
  if (millis() - lastSoil >= 5000) {
    int soil = analogRead(soilPin);
    Serial.println("Soil:" + String(soil));
    lastSoil = millis();
  }
  
  // Auto mode: Scan for flames and follow
  if (mode == 'A') {
    static int direction = 10; // Scan direction (+10 or -10)
    scanPos += direction;
    if (scanPos >= 180 || scanPos <= 0) {
      direction = -direction; // Reverse at limits
      scanPos = constrain(scanPos, 0, 180);
    }
    smallServo.write(scanPos);
    
    if (digitalRead(flamePin) == LOW) { // Flame detected (adjust if HIGH)
      // Blink LED 5 times
      for (int i = 0; i < 5; i++) {
        digitalWrite(ledPin, HIGH);
        delay(200);
        digitalWrite(ledPin, LOW);
        delay(200);
      }
      
      // Aim nozzle
      bigServo.write(scanPos);
      delay(500); // Stabilize servo
      
      // Follow flame using ultrasonic for distance
      while (digitalRead(flamePin) == LOW) {
        long dist = getDistance();
        Serial.println("Dist:" + String(dist)); // Send distance
        
        if (dist > 30) { // Too far, move forward
          moveForward();
        } else if (dist < 15) { // Too close, back up
          moveBackward();
          delay(500);
          stopMotors();
        } else {
          stopMotors();
        }
        
        // Spray water continuously while flame detected
        activatePump();
        
        // Adjust direction if needed (simple: re-scan slightly)
        if (dist > 10 && dist < 100) {
          // Fine-tune scanPos based on flame persistence
          if (digitalRead(flamePin) == HIGH) { // Lost flame, adjust
            scanPos += (direction > 0 ? -5 : 5);
            smallServo.write(scanPos);
            bigServo.write(scanPos);
          }
        }
        
        delay(100); // Loop delay for responsiveness
      }
      
      // Flame extinguished
      deactivatePump();
      stopMotors();
      delay(1000); // Wait before resuming scan
    }
    delay(50); // Smoother scanning
  }
}