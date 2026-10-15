#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "FDMenu.h"
#include "FDBikePawn.generated.h"

class USphereComponent;
class UStaticMesh;
class UStaticMeshComponent;
class UMaterialInstanceDynamic;
class USpringArmComponent;
class UCameraComponent;
class USpotLightComponent;
class UPointLightComponent;
class UInputAction;
class UInputMappingContext;
struct FInputActionValue;
class SWidget;
class UTexture2D;
class AFDTravelPoint;
class AFDWalkerCharacter;
class UFDBikeAudioComponent;

/** 車体色。クロスカブらしい色のほか、BodyColor で好きな色にもできる */
UENUM(BlueprintType)
enum class ECrossCubColor : uint8
{
	Yellow UMETA(DisplayName = "イエロー"),
	White UMETA(DisplayName = "ホワイト"),
	MatteGreen UMETA(DisplayName = "マットグリーン"),
	MatteGray UMETA(DisplayName = "マットグレー"),
	Red UMETA(DisplayName = "レッド"),
	Blue UMETA(DisplayName = "ブルー"),
	Custom UMETA(DisplayName = "カスタム (Body Color の色)"),
};

/** カメラ。V キー (ゲームパッドは右ショルダー) で順に切り替わり、選んだものは次回も使われる */
UENUM(BlueprintType)
enum class EFDBikeCameraMode : uint8
{
	Chase UMETA(DisplayName = "後ろ (遠く)"),
	ChaseNear UMETA(DisplayName = "後ろ (近く)"),
	Helmet UMETA(DisplayName = "ライダーの目線"),
};

/**
 * ホンダ クロスカブ110 を想定したバイク。
 *
 * 物理シミュレーションは使わず、毎フレーム自前で動かす (アーケード寄り、ただし傾きは物理式)。
 * - 前後: エンジン出力 (速度が上がるほど駆動力が落ちる) - 空気抵抗 - 転がり抵抗 - 坂の重力成分
 * - 旋回: 速度に応じてハンドル角を絞り、ホイールベースから旋回率を出す
 * - 傾き: 旋回の遠心力と重力のつり合い (atan(v * 旋回率 / g)) に、なめらかに近づける
 * - 地面: 前輪と後輪の位置から下へトレースし、高さとピッチを合わせる
 *
 * 数値はすべて Blueprint の子クラスやエディタの詳細パネルで調整できる。
 */
UCLASS()
class FUKUOKADRIVE_API AFDBikePawn : public APawn
{
	GENERATED_BODY()

public:
	AFDBikePawn();

	virtual void Tick(float DeltaSeconds) override;
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;
	virtual void PawnClientRestart() override;
	virtual void PossessedBy(AController* NewController) override;
	virtual void UnPossessed() override;

	/** 現在の速度 (km/h)。メーター表示用 */
	UFUNCTION(BlueprintPure, Category = "CrossCub")
	float GetSpeedKmh() const { return SpeedMs * 3.6f; }

	/** 現在の傾き (度、右が正) */
	UFUNCTION(BlueprintPure, Category = "CrossCub")
	float GetLeanDegrees() const { return LeanDeg; }

	/** エンジン回転数 (rpm)。速度とギアから出す (音とメーター用。走りの計算には使わない) */
	UFUNCTION(BlueprintPure, Category = "CrossCub")
	float GetEngineRpm() const { return EngineRpm; }

	/** 今のギア (1-4) */
	UFUNCTION(BlueprintPure, Category = "CrossCub")
	int32 GetGear() const { return Gear + 1; }

	/** カメラを切り替える */
	UFUNCTION(BlueprintCallable, Category = "CrossCub")
	void SetCameraMode(EFDBikeCameraMode Mode);

	/** 人が乗っているか (降りて止めてあるときは false) */
	UFUNCTION(BlueprintPure, Category = "CrossCub")
	bool IsRidden() const { return bRidden; }

	/** 止まっていればバイクを降りて歩く (E キー)。走っている間は降りない */
	UFUNCTION(BlueprintCallable, Category = "CrossCub")
	void GetOff();

	/** その場で止まり、カメラの位置から自由に飛び回る (B キー、もう一度 B で戻る) */
	UFUNCTION(BlueprintCallable, Category = "CrossCub")
	void StartFlying();

	/** バイクの左 (サイドスタンドの側) の、降りて立つ地面の位置と向き */
	FTransform GetDismountTransform() const;

	/** 開始地点 (または最後に道路上にいた地点) に戻す */
	UFUNCTION(BlueprintCallable, Category = "CrossCub")
	void ResetToSafePoint();

	// --- 車体 (クロスカブ110 の公称値に近い値) ---

	/** 車両 + 乗員の質量 (kg)。車両 106kg + 乗員 70kg */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|車体")
	float MassKg = 176.f;

	/** ホイールベース (cm) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|車体")
	float WheelbaseCm = 123.f;

	/** タイヤ半径 (cm)。80/90-17 の外径 576mm */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|車体")
	float WheelRadiusCm = 29.f;

	// --- 見た目 (tools/vehicle/build_crosscub.py で作り、setup_project.py で取り込んだメッシュ) ---
	// 見つからないときはエンジン付属の基本形状で仮の形を出す

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|見た目")
	TSoftObjectPtr<UStaticMesh> BodyMeshAsset;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|見た目")
	TSoftObjectPtr<UStaticMesh> SteeringMeshAsset;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|見た目")
	TSoftObjectPtr<UStaticMesh> WheelMeshAsset;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|見た目")
	TSoftObjectPtr<UStaticMesh> RiderMeshAsset;

	/** 車体色。プレイ中は M キー (ゲームパッドはメニューボタン) のメニューでも選べ、選んだ色は次回も使われる */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|見た目")
	ECrossCubColor BodyColorPreset = ECrossCubColor::Yellow;

	/** BodyColorPreset がカスタムのときの車体色 (リニア) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|見た目", meta = (EditCondition = "BodyColorPreset == ECrossCubColor::Custom"))
	FLinearColor BodyColor = FLinearColor(0.80f, 0.50f, 0.02f);

	/** ライダーを表示する */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|見た目")
	bool bShowRider = true;

	/** ブレーキをかけたときのテールランプの明るさ (ふだんの何倍か) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|見た目")
	float BrakeLightBoost = 4.f;

	// --- エンジン・抵抗 ---

	/** 後輪に伝わる最大出力 (W)。最高出力 5.9kW に伝達効率をかけた値 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|エンジン")
	float MaxPowerW = 5000.f;

	/** 低速 (1速) での最大駆動力 (N)。発進の加速と、止まった所から登れる坂を決める。
	 *  最大トルク 8.5Nm x 1速の総減速比 約26 x 伝達効率 0.9 / タイヤ半径 0.288m で約 700N (約 24 度 = 44% の坂まで発進できる) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|エンジン")
	float MaxDriveForceN = 700.f;

	/** 空気抵抗 0.5 * 空気密度 * Cd * 前面投影面積 (kg/m) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|エンジン")
	float DragCoefficient = 0.36f;

	/** 転がり抵抗係数 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|エンジン")
	float RollingResistance = 0.015f;

	/** ブレーキ全開時の減速度 (m/s^2) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|エンジン")
	float MaxBrakeDecel = 6.5f;

	/** アクセルを離したときのエンジンブレーキ (m/s^2) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|エンジン")
	float EngineBrakeDecel = 0.6f;

	// --- ギア (音のための回転数を出す。クロスカブ110 は 4 速、遠心クラッチ) ---

	/** 1-4 速の変速比 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|ギア")
	TArray<float> GearRatios = {2.615f, 1.555f, 1.136f, 0.916f};

	/** 一次減速比 x 二次減速比 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|ギア")
	float FinalDriveRatio = 4.058f * 2.5f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|ギア")
	float IdleRpm = 1500.f;

	/** 回転の上限 (レブリミット) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|ギア")
	float MaxRpm = 8000.f;

	/** 遠心クラッチがつながりきる回転数。これより遅いときはクラッチが滑り、アクセルで空ぶかしになる */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|ギア")
	float ClutchRpm = 3000.f;

	/** アクセルを少し開けているときのシフトアップの回転数 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|ギア")
	float UpshiftRpmLight = 4200.f;

	/** アクセル全開のときのシフトアップの回転数 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|ギア")
	float UpshiftRpmFull = 6800.f;

	/** この回転数を下回ったらシフトダウン */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|ギア")
	float DownshiftRpm = 2300.f;

	/** 変速にかかる時間 (秒)。そのあいだ駆動力が抜ける */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|ギア")
	float ShiftSeconds = 0.25f;

	// --- カメラ ---

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|カメラ")
	EFDBikeCameraMode CameraMode = EFDBikeCameraMode::Chase;

	/** 止まっているときの視野角 (度) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|カメラ")
	float BaseFov = 80.f;

	/** FovFullSpeedKmh で視野角をこれだけ広げる (速さを感じるように) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|カメラ")
	float SpeedFovAdd = 10.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|カメラ")
	float FovFullSpeedKmh = 90.f;

	/** 後ろのカメラが車体の傾きについていく割合 (0 なら水平のまま、1 なら車体と同じだけ傾く) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|カメラ")
	float ChaseLeanFollow = 0.3f;

	/** ライダーの目線のカメラが車体の傾きについていく割合。人は首で頭を少し起こすので 1 より小さい */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|カメラ")
	float HelmetLeanFollow = 0.6f;

	/** ライダーの目の位置 (車体の座標、地面から cm) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|カメラ")
	FVector HelmetEyeLocation = FVector(0.f, 0.f, 156.f);

	/** ライダーの目線の下向きの角度 (度) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|カメラ")
	float HelmetPitchDeg = -7.f;

	/** カーブの先を見る量。旋回の速さ (度/秒) にこの秒数をかけた角度だけ、曲がる方を向く */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|カメラ")
	float LookIntoTurnSeconds = 0.4f;

	/** カーブの先を見る最大の角度 (度) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|カメラ")
	float MaxLookIntoTurnDeg = 15.f;

	/** 速いとき (FovFullSpeedKmh) のカメラの細かい揺れ (cm) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|カメラ")
	float SpeedShakeCm = 0.6f;

	/** ライダーの目線のときの、エンジンの振動による揺れ (cm) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|カメラ")
	float EngineShakeCm = 0.12f;

	/** ブレーキで前が沈む / 加速で後ろが沈む角度 (度、1G あたり) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|見た目")
	float PitchPerG = 3.f;

	// --- 音 ---

	/** ライダーの目線のときの風切り音の倍率 (ヘルメットの中は風の音が大きい) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|音")
	float HelmetWindScale = 1.5f;

	// --- ハンドリング ---

	/** 低速時の最大ハンドル角 (度) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|ハンドリング")
	float MaxSteerLowSpeedDeg = 28.f;

	/** 高速時の最大ハンドル角 (度) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|ハンドリング")
	float MaxSteerHighSpeedDeg = 3.5f;

	/** この速度 (km/h) で高速時のハンドル角になる */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|ハンドリング")
	float SteerFadeSpeedKmh = 60.f;

	/** ハンドル入力の追従速度 (1/秒) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|ハンドリング")
	float SteerResponse = 4.f;

	/** 傾きの追従速度 (1/秒) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|ハンドリング")
	float LeanResponse = 3.f;

	/** 最大の傾き (度) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|ハンドリング")
	float MaxLeanDeg = 40.f;

	/** ほぼ止まっているときに A/D で向きを変える速さ (度/秒)。足で地面を蹴って向きを変えるつもり */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|ハンドリング")
	float StandstillTurnDegPerSec = 35.f;

	// --- 地面 ---

	/** 地面を探すトレースの上側の長さ (cm) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|地面")
	float GroundTraceUpCm = 150.f;

	/** 地面を探すトレースの下側の長さ (cm) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|地面")
	float GroundTraceDownCm = 300.f;

	/** 坂の重力を計算するときの、前後に地面を測る距離 (cm)。ホイールベースより長く取り、地形の細かい凹凸で止まらないようにする */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|地面")
	float GradeSampleCm = 150.f;

	/** 車体の高さと前後の傾きは、前後にこの長さ (cm) の範囲の地面を何点か測ってならした値にする (サスペンションの代わり)。
	 *  ランドスケープは 1m 格子なので、短い凹凸や格子の折れ目を拾って上下に揺れないようにする。0 なら前輪と後輪の 2 点だけ */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|地面")
	float GroundSmoothHalfLengthCm = 150.f;

	/** ならすときに地面を測る点の数 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|地面", meta = (ClampMin = "2", ClampMax = "15"))
	int32 GroundSmoothSamples = 7;

	/** この高さ (cm) より下に落ちたら (海に入ったら) 開始地点に戻す */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|地面")
	float ResetBelowZCm = -150.f;

	// --- 乗り降り ---

	/** 降りたときに歩くキャラクター */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|乗り降り")
	TSubclassOf<AFDWalkerCharacter> WalkerClass;

	/** この速度 (km/h) より遅ければ降りられる */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|乗り降り")
	float MaxGetOffSpeedKmh = 3.f;

	/** 降りて止めてあるときの傾き (度、サイドスタンドで左へ傾く) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|乗り降り")
	float ParkedLeanDeg = -9.f;

	/** 降りたときに立つ位置の、車体の中心からの左への距離 (cm) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|乗り降り")
	float GetOffSideCm = 85.f;

	/** 画面左上に速度などを表示する */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub")
	bool bShowDebugText = true;

	/** 車体色を用意された色から選ぶ (プレイ中も可) */
	UFUNCTION(BlueprintCallable, Category = "CrossCub")
	void SetBodyColorPreset(ECrossCubColor Preset);

	/** 車体色を好きな色にする (BodyColorPreset はカスタムになる) */
	UFUNCTION(BlueprintCallable, Category = "CrossCub")
	void SetBodyColor(const FLinearColor& Color);

	/** 車体色のメニューを開く / 閉じる */
	UFUNCTION(BlueprintCallable, Category = "CrossCub")
	void ToggleColorMenu();

	// --- ミニマップとファストトラベル ---

	/** 画面の右下にミニマップを出す */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|ミニマップ")
	bool bShowMinimap = true;

	/** 地図の画像 (tools/terrain/build_minimap.py で作り、setup_project.py で取り込んだもの)。北が上 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|ミニマップ")
	TSoftObjectPtr<UTexture2D> MinimapTexture;

	/** 地図の画像の左上 (北西の角) の UE 座標 (cm)。一周コースの地図 (tools/terrain/build_minimap.py が
	 *  out/itoshima_loop/minimap.json に書く範囲) に合わせる */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|ミニマップ")
	FVector2D MinimapWorldMin = FVector2D(-1008000.0, -806400.0);

	/** 地図の画像の右下 (南東の角) の UE 座標 (cm) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|ミニマップ")
	FVector2D MinimapWorldMax = FVector2D(1008000.0, 1209600.0);

	/** ミニマップの直径 (画面の単位) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|ミニマップ")
	float MinimapDiameter = 260.f;

	/** 止まっているときにミニマップに映す半径 (m)。速度が上がると MinimapRadiusFastM まで広がる */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|ミニマップ")
	float MinimapRadiusSlowM = 250.f;

	/** 60km/h 以上でミニマップに映す半径 (m) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|ミニマップ")
	float MinimapRadiusFastM = 600.f;

	/** 音 (エンジン・波・風切り) のオン/オフのメニューを開く / 閉じる (N キー、ゲームパッドは十字キーの下) */
	UFUNCTION(BlueprintCallable, Category = "CrossCub")
	void ToggleSoundMenu();

	/** ファストトラベルのメニューを開く / 閉じる (F キー、ゲームパッドはビューボタン) */
	UFUNCTION(BlueprintCallable, Category = "CrossCub")
	void ToggleTravelMenu();

	/** 行き先へ移る (道路の向きで地面に下ろし、止まった状態から)。R キーで戻る先もそこになる */
	UFUNCTION(BlueprintCallable, Category = "CrossCub")
	void TravelTo(const AFDTravelPoint* Point);

	/** レベルにある行き先を並び順で */
	UFUNCTION(BlueprintCallable, Category = "CrossCub")
	TArray<AFDTravelPoint*> GetTravelPoints() const;

protected:
	virtual void BeginPlay() override;
	virtual void OnConstruction(const FTransform& Transform) override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<USphereComponent> Collision;

	/** 傾き (ロール) をかける軸。見た目のメッシュはすべてこの下 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<USceneComponent> LeanPivot;

	/** ステアリングの軸 (キャスター角だけ後ろへ傾けた、軸の上端) */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<USceneComponent> SteerAxis;

	/** ハンドルまわり。SteerAxis の Z を軸にハンドル角だけ回る。前輪とヘッドライトはこの下 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<UStaticMeshComponent> Steering;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<UStaticMeshComponent> FrontWheel;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<UStaticMeshComponent> RearWheel;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<UStaticMeshComponent> Body;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<UStaticMeshComponent> Rider;

	/** ヘッドライト。日本のバイクは常時点灯なので、昼も点けたまま (昼は露出が高く目立たない)。ハンドルと一緒に向きが変わる */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<USpotLightComponent> Headlight;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<UPointLightComponent> TailLight;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<USpringArmComponent> SpringArm;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<UCameraComponent> Camera;

	/** ライダーの目線のカメラ。車体と一緒に傾く */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<UCameraComponent> HelmetCamera;

	/** エンジン・波・風切りの音 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<UFDBikeAudioComponent> Sound;

private:
	void CreateInputAssets();
	void OnThrottle(const FInputActionValue& Value);
	void OnBrake(const FInputActionValue& Value);
	void OnSteer(const FInputActionValue& Value);
	void OnReset(const FInputActionValue& Value);
	void ApplyPaint();
	void CycleCameraMode();
	void UpdateRiderVisibility();
	/** 速度とアクセルから回転数とギアを決める。変速中は駆動力を抜く割合 (0-1) を返す */
	float UpdateEngine(float DeltaSeconds);
	/** 海の近さ (0-1) を測る (波の音の大きさ) */
	void UpdateSeaAmount(float DeltaSeconds);
	void UpdateCamera(float DeltaSeconds, float YawRateDeg);

	enum class EMenu : uint8 { None, Color, Travel, Sound };
	bool IsMenuOpen(EMenu Kind) const { return Menu.IsOpen() && OpenMenuKind == Kind; }

	void ShowMinimap();
	void HideMinimap();

	bool TraceGround(const FVector& At, FVector& OutPoint, FVector& OutNormal) const;
	bool TraceGroundBetween(const FVector& At, float TopZ, float BottomZ, FVector& OutPoint, FVector& OutNormal) const;
	void UpdateGroundAndPitch(float DeltaSeconds);
	/** 前後 ±GroundSmoothHalfLengthCm の地面に直線を当てはめ、車体の真下の高さと傾き (dZ/dX) を返す。2 点未満なら false */
	bool FitGroundLine(const FVector& Location, const FVector& Forward, float& OutCenterZ, float& OutSlope) const;

	void ApplyAppearance();
	void UpdateAppearance(float DeltaSeconds);
	FVector BikeToSteerLocal(const FVector& BikePoint) const;

	UPROPERTY()
	TObjectPtr<UStaticMesh> FallbackCylinder;

	UPROPERTY()
	TObjectPtr<UStaticMesh> FallbackCube;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UMaterialInstanceDynamic>> PaintMaterials;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> TailLensMaterial;

	UPROPERTY(Transient)
	TObjectPtr<UInputMappingContext> MappingContext;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> ThrottleAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> BrakeAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> SteerAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> ResetAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> ColorMenuAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> TravelMenuAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> GetOffAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> CameraAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> SoundMenuAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> FlyAction;

	/** ミニマップに出している地図 (Slate のブラシは参照を持たないので、ここで持っておく) */
	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> LoadedMinimapTexture;

	FFDMenu Menu;
	EMenu OpenMenuKind = EMenu::None;
	TSharedPtr<SWidget> Minimap;

	/** 瞬間移動のあと、カメラの遅れ (前の場所から追いかけてくる動き) を止めておく残りフレーム数 */
	int32 CameraLagSnapFrames = 0;

	float ThrottleInput = 0.f;
	float BrakeInput = 0.f;
	float SteerInput = 0.f;

	float SpeedMs = 0.f;
	float SteerDeg = 0.f;
	float LeanDeg = 0.f;
	float YawDeg = 0.f;
	float PitchDeg = 0.f;
	/** 坂の角度 (度、登りが正)。GradeSampleCm だけ前後の地面から測る。重力の計算に使う */
	float GradeDeg = 0.f;
	float VerticalSpeedCms = 0.f;
	bool bOnGround = false;
	bool bRidden = true;

	FTransform SafeTransform;
	float SafePointTimer = 0.f;

	// 車輪の回転 (ラジアン) と、回転をかける前の向き (仮の形の円柱は横倒しにするため)
	float WheelSpinRad = 0.f;
	FQuat WheelBaseRotation = FQuat::Identity;
	bool bBrakeLightOn = false;
	float TailLensBaseIntensity = 1.f;

	// エンジン
	float EngineRpm = 1500.f;
	int32 Gear = 0;           // 0 が 1 速
	float ShiftTimer = 0.f;   // 変速中の残り時間 (秒)
	float EngineLoad = 0.f;   // 音に渡すアクセルの開き (変速中は抜ける)
	float SeaAmount = 0.f;    // 海の近さ (0-1)
	float SeaCheckTimer = 0.f;

	// カメラと車体の前後の沈み
	float ForwardAccel = 0.f;  // なめらかにした前後の加速度 (m/s^2)
	float LookYawDeg = 0.f;
	float ShakeTime = 0.f;
};
