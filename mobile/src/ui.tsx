import React from 'react';
import {KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, View} from 'react-native';
import {useSafeAreaInsets} from 'react-native-safe-area-context';
import Ionicons from '@expo/vector-icons/Ionicons';
export const colors = {bg: '#ffffff', surface: '#f4f5f7', ink: '#20242a', muted: '#626b79', border: '#e0e4eb', blue: '#073bb4', danger: '#b42318'};
export function IconButton({name, label, onPress, disabled = false, primary = false}: {name: React.ComponentProps<typeof Ionicons>['name']; label: string; onPress: () => void; disabled?: boolean; primary?: boolean}) {
  return <Pressable accessibilityRole="button" accessibilityLabel={label} accessibilityState={{disabled}} disabled={disabled} onPress={onPress}
    style={({pressed}) => [styles.icon, primary && {backgroundColor: colors.blue}, {opacity: disabled ? .35 : pressed ? .55 : 1}]}>
    <Ionicons name={name} size={22} color={primary ? '#fff' : colors.ink}/>
  </Pressable>;
}
export function Button({title, onPress, disabled = false}: {title: string; onPress: () => void; disabled?: boolean}) {
  return <Pressable accessibilityRole="button" disabled={disabled} onPress={onPress} style={({pressed}) => [styles.button, {opacity: disabled ? .4 : pressed ? .65 : 1}]}><Text style={styles.buttonText}>{title}</Text></Pressable>;
}
export function Sheet({title, closeLabel, onClose, children}: {title: string; closeLabel: string; onClose: () => void; children: React.ReactNode}) {
  const insets = useSafeAreaInsets();
  return <Modal transparent animationType="slide" onRequestClose={onClose}>
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.overlay}><Pressable accessibilityLabel={closeLabel} onPress={onClose} style={StyleSheet.absoluteFill}/>
      <View style={styles.sheet}><View style={styles.row}><Text style={styles.heading}>{title}</Text><IconButton name="close" label={closeLabel} onPress={onClose}/></View>
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{paddingBottom: Math.max(insets.bottom, 20)}}>{children}</ScrollView>
      </View>
    </KeyboardAvoidingView>
  </Modal>;
}
export const styles = StyleSheet.create({
  root: {flex: 1, backgroundColor: colors.bg}, page: {flex: 1, width: '100%', maxWidth: 800, alignSelf: 'center'},
  row: {flexDirection: 'row', alignItems: 'center', gap: 8}, header: {paddingHorizontal: 12, paddingVertical: 4, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border},
  heading: {fontSize: 19, fontWeight: '600', color: colors.ink, flex: 1}, text: {fontSize: 16, color: colors.ink, lineHeight: 24}, muted: {fontSize: 13, color: colors.muted, lineHeight: 20},
  icon: {minWidth: 44, minHeight: 44, borderRadius: 24, alignItems: 'center', justifyContent: 'center'},
  button: {backgroundColor: colors.blue, padding: 14, borderRadius: 16, alignItems: 'center', minHeight: 48, marginVertical: 8}, buttonText: {color: '#fff', fontSize: 16, fontWeight: '600'},
  input: {backgroundColor: colors.surface, borderRadius: 14, paddingHorizontal: 16, paddingVertical: 14, fontSize: 16, color: colors.ink, minHeight: 48, marginBottom: 16},
  label: {color: colors.muted, marginBottom: 8, fontSize: 14}, item: {paddingVertical: 14, paddingHorizontal: 8, minHeight: 48},
  overlay: {flex: 1, backgroundColor: '#00000044', justifyContent: 'flex-end'}, sheet: {width: '100%', maxWidth: 800, alignSelf: 'center', maxHeight: '80%', backgroundColor: colors.bg, padding: 20, borderTopLeftRadius: 24, borderTopRightRadius: 24},
  composer: {borderWidth: 1, borderColor: colors.border, borderRadius: 26, padding: 8, margin: 12}, draft: {fontSize: 16, lineHeight: 23, color: colors.ink, padding: 10, maxHeight: 160, minHeight: 44},
  error: {color: colors.danger, fontSize: 14, paddingHorizontal: 16, paddingVertical: 8},
  bubble: {backgroundColor: colors.surface, padding: 14, borderRadius: 22, borderBottomRightRadius: 6, alignSelf: 'flex-end', maxWidth: '92%', marginVertical: 16},
  avatar: {width: 38, height: 46}, welcome: {padding: 28, alignItems: 'center', marginTop: 40},
});
